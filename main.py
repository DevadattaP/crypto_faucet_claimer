import os
import json
import time
import threading
import signal
from datetime import datetime
from queue import Queue

from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    WebDriverException
)
from webdriver_manager.chrome import ChromeDriverManager


# -------------------------------
# Graceful shutdown flag
# -------------------------------
SHUTDOWN = False

def signal_handler(sig, frame):
    global SHUTDOWN
    print("\n[!] CTRL+C detected — stopping all threads and closing browsers...")
    SHUTDOWN = True

signal.signal(signal.SIGINT, signal_handler)


# -------------------------------
# Utility Logging Helper
# -------------------------------
def log(wallet_idx, faucet_name, message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [Wallet {wallet_idx}] [Faucet {faucet_name}] {message}")


# -------------------------------
# Load environment variables
# -------------------------------
load_dotenv()

WALLETS = [w.strip() for w in os.getenv("WALLET_ADDRESSES", "").split(",") if w.strip()]
MAX_THREADS = int(os.getenv("MAX_THREADS", 8))
HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"
RETRY_COUNT = int(os.getenv("RETRY_COUNT", 3))
RETRY_BACKOFF_SECONDS = int(os.getenv("RETRY_BACKOFF_SECONDS", 5))
FAUCETS_FILE = os.getenv("FAUCETS_FILE", "faucets.json")
LAST_ACCESS_FILE = os.getenv("LAST_ACCESS_FILE", "last_access.json")
DEFAULT_WAIT_TIMEOUT = int(os.getenv("DEFAULT_WAIT_TIMEOUT", 30))
CLOSE_AD_ATTEMPTS = int(os.getenv("CLOSE_AD_ATTEMPTS", 2))
CLOSE_AD_RETRY_DELAY = float(os.getenv("CLOSE_AD_RETRY_DELAY", 1))


# -------------------------------
# Load JSON configurations
# -------------------------------
def load_json_file(path, default):
    if not os.path.exists(path):
        with open(path, "w") as f:
            json.dump(default, f, indent=4)
        return default
    with open(path, "r") as f:
        return json.load(f)


FAUCETS = load_json_file(FAUCETS_FILE, {})
LAST_ACCESS = load_json_file(LAST_ACCESS_FILE, {})


# -------------------------------
# Save last_access.json safely
# -------------------------------
def save_last_access():
    with open(LAST_ACCESS_FILE, "w") as f:
        json.dump(LAST_ACCESS, f, indent=4)


# -------------------------------
# Selenium driver builder
# -------------------------------
def create_driver():
    chrome_options = Options()
    if HEADLESS:
        chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-popup-blocking")
    chrome_options.add_argument("--disable-notifications")

    return webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=chrome_options
    )


# -------------------------------
# Find element by CSS or XPath
# -------------------------------
def find_element(driver, selector):
    if not selector:
        return None
    if selector.startswith("xpath:"):
        path = selector.replace("xpath:", "", 1)
        return driver.find_element(By.XPATH, path)
    return driver.find_element(By.CSS_SELECTOR, selector)


# -------------------------------
# Check last access (24h rule)
# -------------------------------
def can_run(faucet_name, wallet_idx):
    key = f"{faucet_name}:{wallet_idx}"
    entry = LAST_ACCESS.get(key)
    if not entry:
        return True
    last_time = entry["last_access_time"]
    return (time.time() - last_time) >= 86400  # 24 hours


# -------------------------------
# Update last access entry
# -------------------------------
def update_last_access(faucet_name, wallet_idx, message):
    key = f"{faucet_name}:{wallet_idx}"
    LAST_ACCESS[key] = {
        "last_access_time": time.time(),
        "message": message
    }
    save_last_access()


# -------------------------------
# Task Worker (wallet+faucet pair)
# -------------------------------
def run_faucet_task(wallet_idx, faucet_name, config):
    global SHUTDOWN
    if SHUTDOWN:
        return

    wallet = WALLETS[wallet_idx]
    key = f"{faucet_name}:{wallet_idx}"

    log(wallet_idx, faucet_name, "Task started.")

    # Check logical consistency
    if config.get("wallet_address_field") and config.get("connect_wallet_button"):
        raise ValueError(
            f"Faucet '{faucet_name}' has BOTH wallet_address_field and connect_wallet_button defined. Not allowed."
        )

    # Check 24 hour rule
    if not can_run(faucet_name, wallet_idx):
        log(wallet_idx, faucet_name, "Less than 24 hours since last claim. Skipping.")
        return

    retries = 0

    while retries <= RETRY_COUNT and not SHUTDOWN:
        try:
            driver = create_driver()
            driver.set_page_load_timeout(60)

            log(wallet_idx, faucet_name, f"Opening URL: {config['url']}")
            driver.get(config["url"])

            # -------------------------------
            # Close ad popup if configured
            # -------------------------------
            close_btn = config.get("close_ad_button")
            if close_btn:
                for _ in range(CLOSE_AD_ATTEMPTS):
                    try:
                        btn = find_element(driver, close_btn)
                        btn.click()
                        log(wallet_idx, faucet_name, "Closed popup ad.")
                        break
                    except Exception:
                        time.sleep(CLOSE_AD_RETRY_DELAY)

            # -------------------------------
            # Connect wallet (if applicable)
            # -------------------------------
            if config.get("connect_wallet_button"):
                log(wallet_idx, faucet_name, "Clicking connect wallet button.")
                btn = find_element(driver, config["connect_wallet_button"])
                btn.click()
                time.sleep(3)

            # -------------------------------
            # Fill wallet address (if applicable)
            # -------------------------------
            if config.get("wallet_address_field"):
                log(wallet_idx, faucet_name, f"Inserting wallet address: {wallet}")
                field = find_element(driver, config["wallet_address_field"])
                field.clear()
                field.send_keys(wallet)

            # -------------------------------
            # Checkbox
            # -------------------------------
            if config.get("checkbox"):
                try:
                    chk = find_element(driver, config["checkbox"])
                    chk.click()
                    log(wallet_idx, faucet_name, "Checked required checkbox.")
                except Exception:
                    log(wallet_idx, faucet_name, "Checkbox selector provided but not found.")

            # -------------------------------
            # Submit
            # -------------------------------
            log(wallet_idx, faucet_name, "Clicking claim/submit button.")
            submit = find_element(driver, config["submit_button"])
            submit.click()

            # -------------------------------
            # Wait for success/error messages
            # -------------------------------
            timeout = time.time() + DEFAULT_WAIT_TIMEOUT
            success_sel = config.get("success_message_html")
            error_sel = config.get("error_message_html")

            result_message = None

            while time.time() < timeout and not result_message:
                if SHUTDOWN:
                    driver.quit()
                    return

                # Success
                try:
                    if success_sel:
                        s = find_element(driver, success_sel)
                        if s and s.text.strip():
                            result_message = f"SUCCESS: {s.text.strip()}"
                            break
                except NoSuchElementException:
                    pass

                # Error
                try:
                    if error_sel:
                        e = find_element(driver, error_sel)
                        if e and e.text.strip():
                            result_message = f"ERROR: {e.text.strip()}"
                            break
                except NoSuchElementException:
                    pass

                time.sleep(1)

            # If no message found
            if not result_message:
                result_message = "ERROR: No success or error message detected."

            log(wallet_idx, faucet_name, f"Result: {result_message}")
            update_last_access(faucet_name, wallet_idx, result_message)

            driver.quit()
            return  # Done successfully or finished with error

        except WebDriverException as e:
            log(wallet_idx, faucet_name, f"Selenium error: {e}")
        except Exception as e:
            log(wallet_idx, faucet_name, f"Exception: {e}")

        retries += 1
        if retries <= RETRY_COUNT:
            delay = RETRY_BACKOFF_SECONDS * retries
            log(wallet_idx, faucet_name, f"Retrying in {delay} seconds...")
            time.sleep(delay)

    # All retries failed
    update_last_access(faucet_name, wallet_idx, "ERROR: Exhausted retries")
    log(wallet_idx, faucet_name, "Task failed after all retries.")


# -------------------------------
# Thread worker pool
# -------------------------------
def worker_thread(queue):
    global SHUTDOWN
    while not queue.empty() and not SHUTDOWN:
        wallet_idx, faucet_name, config = queue.get()
        run_faucet_task(wallet_idx, faucet_name, config)
        queue.task_done()


# -------------------------------
# Main Execution
# -------------------------------
def main():
    if not WALLETS:
        print("[FATAL] No wallet addresses in .env (WALLET_ADDRESSES).")
        return

    # Build queue of tasks
    task_queue = Queue()

    for faucet_name, config in FAUCETS.items():

        # Validate faucet config
        if config.get("wallet_address_field") and config.get("connect_wallet_button"):
            raise ValueError(
                f"Faucet '{faucet_name}' has BOTH wallet_address_field and connect_wallet_button. Remove one."
            )

        wallet_indexes = config.get("wallet_indexes")

        if wallet_indexes:
            for wi in wallet_indexes:
                if wi < len(WALLETS):
                    task_queue.put((wi, faucet_name, config))
        else:
            # Run for all wallets
            for wi in range(len(WALLETS)):
                task_queue.put((wi, faucet_name, config))

    # Start threads
    threads = []
    for _ in range(min(MAX_THREADS, task_queue.qsize())):
        t = threading.Thread(target=worker_thread, args=(task_queue,))
        t.start()
        threads.append(t)

    # Wait for completion
    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        pass

    print("\nAll tasks finished or stopped.")


if __name__ == "__main__":
    main()
