import os
import json
import time
import threading
import signal
from datetime import datetime
from queue import Queue
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException, WebDriverException
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# Graceful shutdown flag
SHUTDOWN = False

def signal_handler(sig, frame):
    global SHUTDOWN
    print("\n[!] CTRL+C detected — stopping all threads and closing browsers...")
    SHUTDOWN = True

signal.signal(signal.SIGINT, signal_handler)


# Utility Logging Helper
def log(wallet_idx, faucet_name, message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [Wallet {wallet_idx}] [Faucet {faucet_name}] {message}")


# Load environment variables
load_dotenv()

WALLETS = [w.strip() for w in os.getenv("WALLET_ADDRESSES", "").split(",") if w.strip()]
MAX_THREADS = int(os.getenv("MAX_THREADS", 8))
HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"
RETRY_COUNT = int(os.getenv("RETRY_COUNT", 1))
RETRY_BACKOFF_SECONDS = int(os.getenv("RETRY_BACKOFF_SECONDS", 5))
FAUCETS_FILE = os.getenv("FAUCETS_FILE", "faucets.json")
LAST_ACCESS_FILE = os.getenv("LAST_ACCESS_FILE", "last_access.json")
DEFAULT_WAIT_TIMEOUT = int(os.getenv("DEFAULT_WAIT_TIMEOUT", 60))
CLOSE_AD_ATTEMPTS = int(os.getenv("CLOSE_AD_ATTEMPTS", 2))
CLOSE_AD_RETRY_DELAY = float(os.getenv("CLOSE_AD_RETRY_DELAY", 5))
INTERACTION_DELAY = float(os.getenv("INTERACTION_DELAY", 5))
BROWSER = os.getenv("BROWSER", "chrome").lower()
DRIVER_PATH = os.getenv("DRIVER_PATH")
BROWSER_DATA_DIR = os.getenv("BROWSER_DATA_DIR", None)
BROWSER_PROFILE = os.getenv("BROWSER_PROFILE", None)

# Load JSON configurations
def load_json_file(path, default):
    if not os.path.exists(path):
        with open(path, "w") as f:
            json.dump(default, f, indent=4)
        return default
    with open(path, "r") as f:
        return json.load(f)


FAUCETS = load_json_file(FAUCETS_FILE, {})
LAST_ACCESS = load_json_file(LAST_ACCESS_FILE, {})


# Save last_access.json safely
def save_last_access():
    with open(LAST_ACCESS_FILE, "w") as f:
        json.dump(LAST_ACCESS, f, indent=4)


# Selenium driver builder
def create_driver():
    if not DRIVER_PATH or not os.path.exists(DRIVER_PATH):
        raise ValueError(f"Driver not found at {DRIVER_PATH}. Please set DRIVER_PATH in .env")

    if BROWSER == "chrome":
        options = ChromeOptions()
        if HEADLESS:
            options.add_argument("--headless=new")
        if BROWSER_DATA_DIR and BROWSER_PROFILE:
            options.add_argument(f"--user-data-dir={BROWSER_DATA_DIR}")
            options.add_argument(f"--profile-directory={BROWSER_PROFILE}")
        return webdriver.Chrome(service=ChromeService(DRIVER_PATH), options=options)

    elif BROWSER == "edge":
        options = EdgeOptions()
        options.use_chromium = True
        if HEADLESS:
            options.add_argument("--headless=new")
        if BROWSER_DATA_DIR and BROWSER_PROFILE:
            options.add_argument(f"--user-data-dir={BROWSER_DATA_DIR}")
            options.add_argument(f"--profile-directory={BROWSER_PROFILE}")
        return webdriver.Edge(service=EdgeService(DRIVER_PATH), options=options)

    else:
        raise ValueError(f"Invalid BROWSER: {BROWSER}. Use 'chrome' or 'edge'.")


# Check last access (24h rule)
def can_run(faucet_name, wallet_idx):
    key = f"{faucet_name}:{wallet_idx}"
    entry = LAST_ACCESS.get(key)
    if not entry:
        return True

    # If last run was an ERROR → allow immediately
    last_message = entry.get("message", "").lower()
    if last_message.startswith("error"):
        return True

    # If last run was SUCCESS → enforce 24h wait
    last_time = entry["last_access_time"]
    return (time.time() - last_time) >= 86400


# Update last access entry
def update_last_access(faucet_name, wallet_idx, message):
    key = f"{faucet_name}:{wallet_idx}"
    LAST_ACCESS[key] = {
        "last_access_time": time.time(),
        "message": message
    }
    save_last_access()


# Task Worker (wallet+faucet pair)
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
            driver.set_page_load_timeout(120)

            log(wallet_idx, faucet_name, f"Opening URL: {config['url']}")
            driver.get(config["url"])

            # Close ad popup if configured
            close_btn = config.get("close_ad_button")
            if close_btn:
                for _ in range(CLOSE_AD_ATTEMPTS):
                    try:
                        wait = WebDriverWait(driver, 20)
                        btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, close_btn)))
                        btn.click()
                        log(wallet_idx, faucet_name, "Closed popup ad.")
                        break  # Exit loop if closed successfully
                    except Exception:
                        log(wallet_idx, faucet_name, "No popup ad appeared or failed to close.")

            # Connect wallet (if applicable)
            if config.get("connect_wallet_button"):
                log(wallet_idx, faucet_name, "Clicking connect wallet button.")
                wait = WebDriverWait(driver, 20)
                btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, config["connect_wallet_button"])))
                btn.click()
                time.sleep(INTERACTION_DELAY)


            # Fill wallet address (if applicable)
            if config.get("wallet_address_field"):
                log(wallet_idx, faucet_name, f"Inserting wallet address: {wallet}")
                wait = WebDriverWait(driver, 20)
                field = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, config["wallet_address_field"])))
                field.clear()
                field.send_keys(wallet)
                time.sleep(INTERACTION_DELAY)


            # Checkbox
            if config.get("checkbox"):
                try:
                    wait = WebDriverWait(driver, 20)
                    chk = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, config["checkbox"])))
                    chk.click()
                    log(wallet_idx, faucet_name, "Checked required checkbox.")
                except Exception:
                    log(wallet_idx, faucet_name, "Checkbox selector provided but not found or not clickable.")


            # Submit
            log(wallet_idx, faucet_name, "Clicking claim/submit button.")
            wait = WebDriverWait(driver, 20)
            submit = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, config["submit_button"])))
            submit.click()

            # Wait for success/error messages
            timeout = time.time() + DEFAULT_WAIT_TIMEOUT
            success_sel = config.get("success_message_html")
            error_sel = config.get("error_message_html")

            result_message = None

            while time.time() < timeout and not result_message:
                if SHUTDOWN:
                    try:
                        driver.quit()
                    except:
                        pass
                    return

                # Success
                if success_sel:
                    try:
                        s = WebDriverWait(driver, DEFAULT_WAIT_TIMEOUT).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, success_sel))
                        )
                        if s:
                            result_message = f"SUCCESS: {s.text.strip() or 'Success detected'}"
                            break
                    except NoSuchElementException:
                        pass


                # Error
                if error_sel:
                    try:
                        e = WebDriverWait(driver, DEFAULT_WAIT_TIMEOUT).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, error_sel))
                        )
                        if e:
                            result_message = f"ERROR: {e.text.strip() or 'Error detected'}"
                            break
                    except NoSuchElementException:
                        pass

                time.sleep(INTERACTION_DELAY)

            # If no message found
            if not result_message:
                result_message = "ERROR: No success or error message detected."

            log(wallet_idx, faucet_name, f"Result: {result_message}")
            update_last_access(faucet_name, wallet_idx, result_message)

            try:
                driver.quit()
            except:
                pass
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


# Thread worker pool
def worker_thread(queue):
    global SHUTDOWN
    while not queue.empty() and not SHUTDOWN:
        wallet_idx, faucet_name, config = queue.get()
        run_faucet_task(wallet_idx, faucet_name, config)
        queue.task_done()


# Main Execution
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
