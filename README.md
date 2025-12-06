# Daily Faucet Auto-Claimer

Automates daily cryptocurrency faucet claims by visiting each faucet URL, entering wallet addresses, optionally checking checkboxes, submitting forms, and handling popups. The script enforces a 24-hour wait per faucet per wallet and stores last access results.

It supports multiple browsers (Chrome, Edge) and allows running with your regular browser profile, so saved logins, wallets, and extensions are available.

## Repo layout

- `.env` — contains wallet address list and runtime options (ignored by git).
- `.gitignore` — ignores unnecessary files and folders.
- `requirements.txt` — Python dependencies.
- `README.md` — this documentation.
- `last_access.json` — runtime state saved automatically (ignored by git).
- `faucets.json` — faucet definitions and HTML/CSS/XPath selectors.
- `main.py` — main program.

## Installing

1. Recommended to create a Python 3.9+ virtual environment and activate it.

2. Install dependencies:

    ```bash
    pip install -r requirements.txt
    ```

3. Configure `.env`

    Create .env with at least:

    ```bash
    WALLET_ADDRESSES=0xWallet1,0xWallet2
    MAX_THREADS=1
    HEADLESS=false
    RETRY_COUNT=0
    RETRY_BACKOFF_SECONDS=5
    DEFAULT_WAIT_TIMEOUT=60
    CLOSE_AD_ATTEMPTS=1
    CLOSE_AD_RETRY_DELAY=5
    BROWSER=edge
    DRIVER_PATH=./msedgedriver.exe
    BROWSER_DATA_DIR=C:\Users\<USERNAME>\AppData\Local\Microsoft\Edge\User Data
    BROWSER_PROFILE=Default
    ```

    | Variable                | Description                                                                  |
    | ----------------------- | ---------------------------------------------------------------------------- |
    | `WALLET_ADDRESSES`      | Comma-separated wallet addresses.                                            |
    | `MAX_THREADS`           | Maximum number of parallel browser threads (set 1 for sequential execution). |
    | `HEADLESS`              | `true` or `false` — run browser in headless mode.                            |
    | `RETRY_COUNT`           | Number of retries per faucet on failure.                                     |
    | `RETRY_BACKOFF_SECONDS` | Base backoff seconds (multiplied per retry).                                 |
    | `DEFAULT_WAIT_TIMEOUT`  | Seconds to wait for success/error messages.                                  |
    | `CLOSE_AD_ATTEMPTS`     | Number of attempts to close popup ads.                                       |
    | `CLOSE_AD_RETRY_DELAY`  | Delay (seconds) between retrying ad close.                                   |
    | `BROWSER`               | Browser to use (`chrome` or `edge`).                                         |
    | `DRIVER_PATH`           | Path to the ChromeDriver or EdgeDriver executable.                           |
    | `BROWSER_DATA_DIR`      | Path to your browser’s user data directory (keeps your profile/logins).      |
    | `BROWSER_PROFILE`       | Browser profile folder name (e.g., `Default`).                               |

4. Configure `faucets.json`

    Each faucet entry:

    ```json
    {
        "faucet_name": {
            "url": "",
            "wallet_address_field": "#wallet",
            "connect_wallet_button": "#connect",
            "checkbox": "#agree",                    // optional
            "submit_button": "#submit",
            "close_ad_button": "#ad-close",          // optional
            "error_message_html": ".error",
            "success_message_html": ".success",
            "wallet_indexes": [0, 1, 3]              // optional
        }
    }

    ```

    - `wallet_index` is optional. If omitted, the program assigns faucet with all wallets.
    - Either of the `wallet_address_field` or `connect_wallet_button` should be present. If both connect_wallet_button and wallet_address_field are present (non-null), the program will raise an error at startup — this prevents ambiguous/unsupported flows.
    - Use xpath: prefix to provide XPath selectors (e.g. "xpath://input[@name='wallet']"). Otherwise selectors are treated as CSS selectors.

5. `last_access.json` format
    Initialize as:

    ```json
    {}
    ```

    Automatically created and updated during runtime as:

    ```json
    {
        "<faucet_name>:<wallet_index>": {
            "last_access_time": 1733424000,
            "message": "SUCCESS: ..."
        }
    }
    ```

    - Example key: example_faucet:1 — faucet example_faucet for wallet index 1.
    - Timestamps are UNIX milliseocnds.
    - Prevents claiming the same faucet within 24 hours.

## Run

```bash
python main.py
```

- Press `Ctrl+C` to stop; the program will attempt a graceful shutdown.
- With `MAX_THREADS=1`, the bot runs one faucet at a time (recommended for stability, captcha handling, and wallet interactions).

## Features

- Supports Chrome and Edge browsers.
- Runs with your regular browser profile — preserves logins, wallets, and extensions.
- Handles popup ads automatically.
- Waits for elements using dynamic Selenium waits (WebDriverWait + expected_conditions) for stability.
- Enforces 24-hour wait per faucet per wallet.
- Optional checkbox handling and form submission automation.
- Tracks success/error messages and saves them in last_access.json.
- Configurable retry/backoff for unreliable faucets.

> [!NOTE]
> Chrome or Edge must be installed on your system.\
> By checking your browser version, download driver from official website.\
> For example- For Edge, download msedgedriver.exe or point `DRIVER_PATH` to the driver binary.\
> If you want the script to run headless, set `HEADLESS=true`. Otherwise, your real browser opens with your profile.

## Contributing

Contributions are welcome! You can help improve the bot by:

- Adding support for more faucets/testnet tokens.
- Improving reliability and handling of captcha or dynamic page elements.
- Optimizing wait times and interaction delays for smoother automation.
- Fixing bugs or adding new features.

Feel free to fork the repository, make improvements, and submit a pull request. Your help makes the auto-claimer more robust and useful for everyone!
