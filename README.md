# Daily Faucet Auto-Claimer

Automates daily faucet claims by visiting each faucet URL, entering wallet address, checking optional checkboxes and submitting the form. The script enforces a 24-hour wait per faucet and stores last access results.

## Repo layout

- `.env` — contains wallet address list and runtime options (ignored by git).
- `.gitignore` — ignores `.env` and `last_access.json`.
- `requirements.txt` — Python deps.
- `README.md` — this file.
- `last_access.json` — saved runtime state (ignored by git).
- `faucets.json` — faucet definitions and selectors (you will fill HTML selectors).
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
    WALLET_ADDRESSES=addr1,addr2
    MAX_THREADS=8
    HEADLESS=true
    RETRY_COUNT=3
    RETRY_BACKOFF_SECONDS=5
    DEFAULT_WAIT_TIMEOUT=60
    ```

    - `WALLET_ADDRESSES` is a comma separated list.
    - `MAX_THREADS` maximum parallel browser threads.
    - `HEADLESS` true/false (Chrome headless).
    - `RETRY_COUNT` number of retries on error per faucet submit.
    - `RETRY_BACKOFF_SECONDS` base backoff seconds (exponential backoff applied per retry).
    - `DEFAULT_WAIT_TIMEOUT` seconds to wait for success/error msg

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

## Run

```bash
python main.py
```

Press `Ctrl+C` to stop; the program will attempt a graceful shutdown.

> [!NOTE]
> I used Selenium + webdriver-manager to manage ChromeDriver automatically.
>
> You will need Chrome/Chromium installed on the machine.
