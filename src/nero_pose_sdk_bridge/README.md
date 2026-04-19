# nero_pose_sdk_bridge

Pure Python CLI demo for Nero + Xvisio.

This folder does not depend on ROS.

It now provides:

- Nero arm startup flow matching `pyAgxArm/web_control/app.py`
- automatic arm connect -> enable -> `set_normal_mode()` -> wait for CAN feedback
- automatic move to initial joint pose `[0.0, -90.0, 0.0, 123.0, 0.0, 0.0, 0.0]`
- current TCP pose output relative to `base_link`
- Xvisio wireless controller 6DoF pose polling through `XvisioSDK/libwirelessController.so`
- start-follow trigger only after a controller key event is received
- optional manual TCP target input for quick motion tests

## Files

- `pose_bridge.py`: reusable Nero SDK bridge with startup/feedback handling
- `xvisio_wireless.py`: `ctypes` wrapper for the Xvisio wireless controller SDK
- `demo.py`: pure command line demo
- `tcp_pose_demo.py`: simple TCP pose test based on the SDK demo

## Default assumptions

- CAN interface is already activated on boot
- CAN channel name is `nero_can`
- Xvisio SDK library is at `/home/lz/nero_ws/XvisioSDK/libwirelessController.so`
- right controller pose is read by default, following the `XvisioSDK/test.cpp` example

## Quick start

```bash
cd /home/lz/nero_ws
python3 src/nero_pose_sdk_bridge/demo.py
```

中文启动说明：

```bash
cd /home/lz/nero_ws
python3 src/nero_pose_sdk_bridge/demo.py
```

启动后程序会按下面顺序执行：

- 连接机械臂
- 给机械臂上使能
- 调用 `set_normal_mode()` 打开 CAN 推送
- 等待机械臂反馈稳定
- 机械臂移动到初始关节位 `[0.0, -90.0, 0.0, 123.0, 0.0, 0.0, 0.0]`
- 启动 Xvisio 6DoF 数据接收
- 等待手柄按键触发
- 按键后开始用 Xvisio 的位姿驱动机械臂末端跟随

如果只想看数据、不让机械臂进入跟随，可以使用：

```bash
cd /home/lz/nero_ws
python3 src/nero_pose_sdk_bridge/demo.py --monitor-only
```

## 中文补充说明

### 当前跟随逻辑

当前程序不是启动后立刻让机械臂跟随 Xvisio，而是分成两个阶段：

1. 机械臂初始化阶段

- 连接 `nero_can`
- 机械臂上使能
- 调用 `set_normal_mode()` 打开 CAN 推送
- 等待关节反馈稳定
- 回到初始关节位 `[0.0, -90.0, 0.0, 123.0, 0.0, 0.0, 0.0]`

2. Xvisio 跟随阶段

- 程序持续接收 `xv_wireless_controller_get_6dof()` 的结果
- 在收到一次按键事件之前，只监听手柄数据，不给机械臂发送跟随命令
- 收到按键后，把“当前手柄位姿”和“当前机械臂 TCP 位姿”一起记成参考点
- 从这个参考点开始，用手柄相对变化去驱动机械臂末端 TCP 跟随

### Xvisio 的 xyz 和四元数现在是怎么用的

Xvisio 返回的数据包括：

- `position`：`x y z`
- `quaternion`：`qx qy qz qw`

当前程序的默认行为是：

- `xyz`：参与跟随
- 四元数：默认不参与跟随

也就是说，默认启动命令下：

- 机械臂末端会跟随手柄的相对位置变化
- 机械臂末端姿态默认保持参考姿态不变

如果需要连姿态一起跟，可以这样启动：

```bash
cd /home/lz/nero_ws
python3 src/nero_pose_sdk_bridge/demo.py --follow-orientation
```

这时程序会额外使用手柄四元数的相对变化去驱动末端姿态。

### 需要特别注意

- 现在是“相对跟随”，不是“机械臂末端绝对等于 Xvisio 当前绝对位姿”
- 按键前只监听，不移动机械臂
- 按键后才会锁定参考点并开始跟随
- 如果发现某个轴方向相反，可以调 `--position-signs` 或 `--rotation-signs`
- 如果发现动作过大或过小，可以调 `--position-scale` 或 `--rotation-scale`

### 常用启动方式

1. 默认启动

```bash
cd /home/lz/nero_ws
python3 src/nero_pose_sdk_bridge/demo.py
```

效果：

- 机械臂回初始位
- 等待手柄按键
- 按键后开始位置跟随
- 姿态默认不跟

2. 打开姿态跟随

```bash
cd /home/lz/nero_ws
python3 src/nero_pose_sdk_bridge/demo.py --follow-orientation
```

效果：

- 机械臂回初始位
- 等待手柄按键
- 按键后同时跟随 `xyz + 四元数`

3. 只允许位移，不允许旋转

```bash
cd /home/lz/nero_ws
python3 src/nero_pose_sdk_bridge/demo.py --position-only
```

效果：

- 机械臂回初始位
- 等待启动键触发
- 只跟随位置变化
- 姿态保持当前参考姿态

4. 只允许旋转，不允许位移

```bash
cd /home/lz/nero_ws
python3 src/nero_pose_sdk_bridge/demo.py --rotation-only
```

效果：

- 机械臂回初始位
- 等待启动键触发
- 只跟随姿态变化
- TCP 位置保持当前参考位置

5. 只监控，不跟随

```bash
cd /home/lz/nero_ws
python3 src/nero_pose_sdk_bridge/demo.py --monitor-only
```

效果：

- 机械臂完成连接、使能和回初始位
- 只打印机械臂 TCP 和 Xvisio 数据
- 不进入跟随

6. 手动输入末端目标位姿

```bash
cd /home/lz/nero_ws
python3 src/nero_pose_sdk_bridge/demo.py --interactive-target
```

效果：

- 启动后可手动输入 `x y z roll pitch yaw`
- 方便单独验证 SDK 的 TCP 控制链路

7. 简单 TCP pose 测试

```bash
cd /home/lz/nero_ws
python3 src/nero_pose_sdk_bridge/tcp_pose_demo.py
```

效果：

- 连接机械臂并上使能
- 设置 TCP offset
- 打印当前 TCP pose
- 打印当前 flange pose
- 打印 `flange -> tcp` 转换结果

如果要直接测试一个目标末端位姿，可以使用：

```bash
cd /home/lz/nero_ws
python3 src/nero_pose_sdk_bridge/tcp_pose_demo.py \
  --target-tcp -0.45 -0.0 0.45 -1.5708 0.0 -3.14159
```

这个 demo 会调用：

- `robot.set_tcp_offset(...)`
- `robot.get_tcp_pose()`
- `robot.get_flange_pose()`
- `robot.get_flange2tcp_pose(...)`
- `robot.get_tcp2flange_pose(...)`
- `robot.move_p(...)`

### 常用调参

调整位置跟随比例：

```bash
python3 src/nero_pose_sdk_bridge/demo.py \
  --position-scale 1.0 1.0 1.0
```

反转某个位置轴方向，例如反转 Y 轴：

```bash
python3 src/nero_pose_sdk_bridge/demo.py \
  --position-signs 1 -1 1
```

打开姿态跟随并反转偏航方向：

```bash
python3 src/nero_pose_sdk_bridge/demo.py \
  --follow-orientation \
  --rotation-signs 1 1 -1
```

只允许位移，不允许姿态变化：

```bash
python3 src/nero_pose_sdk_bridge/demo.py \
  --position-only
```

只允许姿态变化，不允许位置变化：

```bash
python3 src/nero_pose_sdk_bridge/demo.py \
  --rotation-only
```

限制最大跟随范围：

```bash
python3 src/nero_pose_sdk_bridge/demo.py \
  --max-position-delta 0.10 0.10 0.10 \
  --max-orientation-delta-deg 20 20 30
```

### 终端输出怎么看

常见输出含义如下：

- `current tcp pose`：当前机械臂末端 TCP 位姿
- `xvisio pose`：当前手柄 6DoF 数据
- `xvisio device`：手柄电量、温度、序列号信息
- `waiting for controller key press to start tracking`：正在等按键开始跟踪
- `tracking start key received`：已检测到按键事件
- `follow reference locked`：已经锁定参考手柄位姿和参考 TCP 位姿
- `follow target tcp pose`：当前发给机械臂的末端目标位姿

### 联调建议

- 第一次联调建议先用 `--monitor-only` 确认 Xvisio 数据在正常刷新
- 然后用默认模式，只验证位置跟随
- 确认 `xyz` 方向都正确后，再加 `--follow-orientation`
- 如果某个轴方向反了，优先调 `--position-signs` 或 `--rotation-signs`
- 如果机械臂动作太大，先减小 `--position-scale`，再减小 `--max-position-delta`

The startup sequence is:

```text
connect arm
enable arm
set_normal_mode
wait for CAN push / joint feedback
move to initial joint pose
start Xvisio 6DoF polling
wait for controller key press
start TCP follow
```

After startup, the terminal will continuously print:

- current Nero TCP pose
- Xvisio controller position + quaternion
- Xvisio battery / temperature information
- follow target TCP pose after tracking starts

## Useful options

Use the left controller:

```bash
python3 src/nero_pose_sdk_bridge/demo.py --controller-side left
```

Use a custom SDK library path:

```bash
python3 src/nero_pose_sdk_bridge/demo.py \
  --xvisio-lib /absolute/path/to/libwirelessController.so
```

Enable manual target TCP input:

```bash
python3 src/nero_pose_sdk_bridge/demo.py --interactive-target
```

Only monitor Xvisio + robot state and do not start follow:

```bash
python3 src/nero_pose_sdk_bridge/demo.py --monitor-only
```

Override the initial joint position:

```bash
python3 src/nero_pose_sdk_bridge/demo.py \
  --initial-joints-deg 0 -90 0 123 0 0 0
```

Optional TCP offset example:

```bash
python3 src/nero_pose_sdk_bridge/demo.py \
  --tcp-offset 0.0 0.0 0.10 0.0 0.0 0.0
```

When `--interactive-target` is enabled, input one target TCP pose per line:

```text
0.35 0.00 0.30 3.14159 0.0 0.0
```

The six values mean:

```text
x y z roll pitch yaw
```

Units:

- `x y z`: meters
- `roll pitch yaw`: radians

All TCP poses are expressed in the `base_link` frame.
