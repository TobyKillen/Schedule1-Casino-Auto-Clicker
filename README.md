# Schedule 1 Auto Clicker

A simple Windows auto clicker made mainly for repeatedly using a single casino machine in **Schedule I**.

By default, it presses **E every 3 seconds**. Press **F1** at any time to enable or disable it.

## Download

1. Open the [latest release](https://github.com/TobyKillen/Schedule1-Casino-Auto-Clicker/releases/latest).
2. Select the latest version.
3. Download `Schedule1AutoClicker.exe` or the versioned Windows ZIP.
4. Extract the ZIP if you downloaded it.
5. Run `Schedule1AutoClicker.exe`.

SHA-256 checksums are attached to every release as `SHA256SUMS.txt`.

No Python installation or additional setup is required.

> Windows SmartScreen may warn you because the executable is not code-signed. Select **More info**, confirm that you trust the download, and choose **Run anyway**.

## How to use

1. Open `Schedule1AutoClicker.exe`.
2. Leave **E** selected for the casino interaction key.
3. Set how often the key should be pressed and how long it should be held.
4. Click **Apply settings**.
5. Return to Schedule I and aim at the casino machine.
6. Press **F1** to enable the auto clicker.
7. Press **F1** again to stop it.

The key and enable/disable hotkey can both be changed from the application.

## Troubleshooting

### It works in Windows but not in Schedule I

Keep Schedule I focused while the auto clicker is enabled. If the game is running as administrator, run `Schedule1AutoClicker.exe` as administrator too.

### F1 does not enable it

Another application may already be using F1 as a global hotkey. Select a different toggle hotkey in the application and click **Apply settings**.

### Where are the logs?

Diagnostic logs are stored at:

```text
%LOCALAPPDATA%\Schedule1AutoClicker\logs\Schedule1AutoClicker.log
```

## Disclaimer

Use this utility responsibly and at your own risk. Schedule I and its logo are properties of TVGS. This is an unofficial fan-made utility and is not affiliated with or endorsed by TVGS.
