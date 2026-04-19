# Nero Web Control

This folder contains a lightweight HTTP web controller for Nero.

## What it does

- Serves a simple mobile-friendly web page
- Shows whether CAN is connected, whether the arm feedback is ready, whether the arm is enabled, and whether it has returned to shutdown-prep position
- Exposes four preset buttons:
  - `Initial`
  - `Ready`
  - `Work`
  - `ShutdownPrep`
- Lets you enable the arm from the page after the arm is ready
- Lets you disable the arm from the page, but only after the arm has returned to `ShutdownPrep`
- Uses `pyAgxArm` directly over CAN

## Protocol

The web page uses `HTTP`.

## Editable config

Edit [`config.json`](./config.json):

- `server.host`: IP/interface to bind, for example `0.0.0.0`
- `server.port`: HTTP port, for example `8080`
- `robot.can_port`: CAN interface, for example `nero_can`
- `robot.firmware_version`: `default` or `v111`
- `robot.command_repeats`: how many times to re-send one target right after button press
- `robot.command_repeat_interval`: seconds between those initial sends
- `robot.command_refresh_interval`: seconds between refresh sends while the arm is still moving
- `positions_deg`: preset positions in degrees, including `ShutdownPrep`

## Run

```bash
cd /home/lz/nero_ws/pyAgxArm/web_control
./start_web.sh
```

Then open from your phone browser:

```text
http://<jetson-ip>:8080
```

## Notes

- Your phone and Jetson must be in the same LAN.
- The script assumes CAN is already activated before opening the page.
- The web page now handles readiness check, enable, move, and disable flow; you do not need a separate auto-enable / auto-move startup script for this flow.
- The server keeps the SDK connection open while it is running.

## Auto-activate CAN without password prompts

If you want the CAN port to come up automatically at boot, use the included `systemd` unit:

1. Edit [`nero-can.env`](./nero-can.env) and confirm:
   - `CAN_PORT` matches `config.json`
   - Recommended value: `nero_can` for the USB-CAN adapter alias
   - `BITRATE` is correct
   - `USB_ADDRESS` is correct for your adapter, or clear it if you only have one CAN adapter
   - `RETRY_INTERVAL` and `MAX_WAIT_SECONDS` fit your boot timing
2. Install and enable the service once:

```bash
sudo cp /home/lz/nero_ws/pyAgxArm/web_control/nero-can.service /etc/systemd/system/nero-can.service
sudo systemctl daemon-reload
sudo systemctl enable --now nero-can.service
```

3. Check status:

```bash
systemctl status nero-can.service
ip link show nero_can
```

After this one-time setup, boot-time CAN activation no longer needs you to enter a password manually.
The CAN service now retries activation until the interface is really `UP`, which is useful when the robot or adapter takes time to finish booting.

## Auto-start the web control on boot

If you also want the web page itself to start automatically at boot, install the included web service:

```bash
sudo cp /home/lz/nero_ws/pyAgxArm/web_control/nero-web.service /etc/systemd/system/nero-web.service
sudo systemctl daemon-reload
sudo systemctl enable --now nero-web.service
```

Check status:

```bash
systemctl status nero-web.service
```

Recommended boot flow:

1. `nero-can.service` finds the USB-CAN adapter by `USB_ADDRESS` and renames it to `nero_can`
2. `nero-web.service` starts `app.py`
3. The page opens with CAN state monitoring already active

The `CAN 连接` indicator in the page is based on whether the SDK successfully connects to the SocketCAN interface. When the CAN port is up but arm feedback has not arrived yet, the page should show CAN connected and summary text like “已连接 CAN，等待机械臂反馈”.
