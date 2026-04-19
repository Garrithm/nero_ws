#!/usr/bin/env python3
import json
import math
import sys
import threading
import time
from functools import partial
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse


WEB_CONTROL_DIR = Path(__file__).resolve().parent
REPO_ROOT = WEB_CONTROL_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pyAgxArm import AgxArmFactory, ArmModel, NeroFW, create_agx_arm_config


HTML_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Nero 控制面板</title>
  <style>
    :root {
      --bg: #f5f1e8;
      --panel: rgba(255, 252, 246, 0.92);
      --ink: #1f1a14;
      --muted: #6f6558;
      --line: rgba(74, 56, 41, 0.16);
      --accent: #b5542f;
      --accent-dark: #7a351d;
      --enable: #2f7a49;
      --enable-dark: #1f5a34;
      --disable: #b03b2e;
      --disable-dark: #7d241b;
      --success: #226c48;
      --danger: #9f2f23;
      font-family: "Segoe UI", "PingFang SC", "Noto Sans SC", sans-serif;
    }

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      min-height: 100vh;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(214, 153, 98, 0.24), transparent 30%),
        radial-gradient(circle at bottom right, rgba(181, 84, 47, 0.18), transparent 28%),
        linear-gradient(135deg, #f7f3ea 0%, #efe7d8 100%);
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 20px;
    }

    .shell {
      width: min(520px, 100%);
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 28px;
      padding: 28px 22px 22px;
      box-shadow: 0 18px 40px rgba(67, 47, 28, 0.12);
      backdrop-filter: blur(10px);
    }

    h1 {
      margin: 0 0 8px;
      font-size: clamp(28px, 5vw, 40px);
      line-height: 1.05;
    }

    p {
      margin: 0;
      color: var(--muted);
      line-height: 1.5;
    }

    .stack {
      display: grid;
      gap: 14px;
      margin-top: 24px;
    }

    .positions-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
      margin-top: 24px;
    }

    .jog-panel {
      margin-top: 20px;
    }

    .jog-panel-title {
      margin: 0 0 12px;
      font-size: 18px;
      color: var(--muted);
    }

    .jog-list {
      display: flex;
      flex-direction: column;
      gap: 10px;
    }

    .jog-line {
      display: grid;
      grid-template-columns: 56px 1fr 1fr;
      gap: 10px;
      align-items: stretch;
    }

    .jog-line .jog-label {
      font-size: 15px;
      font-weight: 600;
      color: var(--muted);
      display: flex;
      align-items: center;
    }

    .jog-line button {
      padding: 14px 12px;
      font-size: 20px;
      user-select: none;
      touch-action: none;
    }

    .status-panel {
      margin-top: 22px;
      border-radius: 22px;
      padding: 18px 16px;
      background: rgba(255, 255, 255, 0.72);
      border: 1px solid var(--line);
    }

    .status-panel h2 {
      margin: 0 0 12px;
      font-size: 18px;
    }

    .status-list {
      display: grid;
      gap: 10px;
    }

    .status-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      font-size: 15px;
    }

    .status-row span:first-child {
      color: var(--muted);
    }

    .pill {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 86px;
      padding: 6px 12px;
      border-radius: 999px;
      font-size: 13px;
      font-weight: 700;
      background: rgba(111, 101, 88, 0.12);
      color: var(--muted);
    }

    .pill.ok {
      background: rgba(34, 108, 72, 0.14);
      color: var(--success);
    }

    .pill.warn {
      background: rgba(181, 84, 47, 0.14);
      color: var(--accent-dark);
    }

    .pill.err {
      background: rgba(159, 47, 35, 0.14);
      color: var(--danger);
    }

    .status-tip {
      margin-top: 14px;
      padding: 12px 14px;
      border-radius: 14px;
      background: rgba(255, 248, 239, 0.9);
      border: 1px solid rgba(181, 84, 47, 0.18);
      line-height: 1.55;
      font-size: 15px;
      font-weight: 700;
      color: var(--ink);
    }

    button {
      width: 100%;
      border: 0;
      border-radius: 20px;
      padding: 18px 18px;
      text-align: center;
      color: #fff8ef;
      background: linear-gradient(135deg, var(--accent) 0%, var(--accent-dark) 100%);
      box-shadow: 0 12px 24px rgba(122, 53, 29, 0.16);
      font-size: 20px;
      font-weight: 700;
      cursor: pointer;
      transition: transform 140ms ease, box-shadow 140ms ease, opacity 140ms ease;
    }

    button:hover {
      transform: translateY(-1px);
      box-shadow: 0 16px 28px rgba(122, 53, 29, 0.2);
    }

    button:disabled {
      opacity: 0.55;
      cursor: wait;
      transform: none;
      box-shadow: none;
    }

    button.secondary {
      color: var(--ink);
      background: linear-gradient(135deg, #f3eadc 0%, #e4d6c1 100%);
      box-shadow: 0 12px 24px rgba(92, 72, 48, 0.14);
    }

    button.secondary.enable {
      color: #f4fff7;
      background: linear-gradient(135deg, var(--enable) 0%, var(--enable-dark) 100%);
      box-shadow: 0 12px 24px rgba(31, 90, 52, 0.18);
    }

    button.secondary.disable {
      color: #fff5f2;
      background: linear-gradient(135deg, var(--disable) 0%, var(--disable-dark) 100%);
      box-shadow: 0 12px 24px rgba(125, 36, 27, 0.18);
    }

    button.secondary.disabled-state {
      color: #7d7060;
      background: linear-gradient(135deg, #ebe3d8 0%, #ddd2c1 100%);
      box-shadow: 0 12px 24px rgba(120, 104, 82, 0.12);
    }

    .button-title {
      display: block;
      font-size: 20px;
      font-weight: 700;
    }

    .status-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
      margin-top: 20px;
    }

    .status {
      border-radius: 18px;
      padding: 14px 16px;
      background: rgba(255, 255, 255, 0.72);
      border: 1px solid var(--line);
      min-height: 82px;
    }

    .status h2 {
      margin: 0 0 8px;
      font-size: 15px;
      color: var(--muted);
    }

    .status pre {
      margin: 0;
      white-space: nowrap;
      overflow-x: auto;
      line-height: 1.5;
      font-family: "Segoe UI", "PingFang SC", "Noto Sans SC", sans-serif;
    }

    .status.ok pre {
      color: var(--success);
    }

    .status.err pre {
      color: var(--danger);
    }

    @media (max-width: 560px) {
      .status-grid {
        grid-template-columns: 1fr;
      }
    }
  </style>
</head>
<body>
  <main class="shell">
    <h1>Nero 控制</h1>

    <section class="status-panel">
      <h2>机械臂状态</h2>
      <div class="status-list">
        <div class="status-row">
          <span>CAN 连接</span>
          <strong id="connection-status" class="pill">检查中</strong>
        </div>
        <div class="status-row">
          <span>机械臂准备状态</span>
          <strong id="ready-status" class="pill">检查中</strong>
        </div>
        <div class="status-row">
          <span>使能状态</span>
          <strong id="enable-status" class="pill">检查中</strong>
        </div>
      </div>
      <div id="status-tip" class="status-tip">正在读取机械臂状态...</div>
    </section>

    <section class="stack">
      <button id="toggle-enable-button" class="secondary" type="button">
        <span class="button-title">未就绪</span>
      </button>
    </section>

    <section class="positions-grid">
      <button data-position="初始位置">初始位置</button>
      <button data-position="断电位置">断电位置</button>
      <button data-position="拍摄高位">拍摄高位</button>
      <button data-position="拍摄低位">拍摄低位</button>
      <button data-position="抓取锥桶">抓取锥桶</button>
      <button data-position="提取锥桶">提取锥桶</button>
      <button data-position="放下锥桶">放下锥桶</button>
    </section>

    <section class="jog-panel" aria-label="关节微调">
      <h2 class="jog-panel-title">关节微调</h2>
      <div class="jog-list">
        <div class="jog-line" data-joint="1">
          <span class="jog-label">关节1</span>
          <button type="button" class="secondary jog-btn" data-dir="-1">−</button>
          <button type="button" class="secondary jog-btn" data-dir="1">+</button>
        </div>
        <div class="jog-line" data-joint="2">
          <span class="jog-label">关节2</span>
          <button type="button" class="secondary jog-btn" data-dir="-1">−</button>
          <button type="button" class="secondary jog-btn" data-dir="1">+</button>
        </div>
        <div class="jog-line" data-joint="3">
          <span class="jog-label">关节3</span>
          <button type="button" class="secondary jog-btn" data-dir="-1">−</button>
          <button type="button" class="secondary jog-btn" data-dir="1">+</button>
        </div>
        <div class="jog-line" data-joint="4">
          <span class="jog-label">关节4</span>
          <button type="button" class="secondary jog-btn" data-dir="-1">−</button>
          <button type="button" class="secondary jog-btn" data-dir="1">+</button>
        </div>
        <div class="jog-line" data-joint="5">
          <span class="jog-label">关节5</span>
          <button type="button" class="secondary jog-btn" data-dir="-1">−</button>
          <button type="button" class="secondary jog-btn" data-dir="1">+</button>
        </div>
        <div class="jog-line" data-joint="6">
          <span class="jog-label">关节6</span>
          <button type="button" class="secondary jog-btn" data-dir="-1">−</button>
          <button type="button" class="secondary jog-btn" data-dir="1">+</button>
        </div>
        <div class="jog-line" data-joint="7">
          <span class="jog-label">关节7</span>
          <button type="button" class="secondary jog-btn" data-dir="-1">−</button>
          <button type="button" class="secondary jog-btn" data-dir="1">+</button>
        </div>
      </div>
    </section>

    <section class="status-grid">
      <section id="move-status" class="status">
        <h2>动作结果</h2>
        <pre id="move-status-text">等待操作</pre>
      </section>
      <section id="current-status" class="status">
        <h2>当前角度</h2>
        <pre id="current-status-text">正在读取...</pre>
      </section>
    </section>
  </main>

  <script>
    const POSITION_LABELS = {
      初始位置: "初始位置",
      断电位置: "断电位置",
      拍摄高位: "拍摄高位",
      拍摄低位: "拍摄低位",
      抓取锥桶: "抓取锥桶",
      提取锥桶: "提取锥桶",
      放下锥桶: "放下锥桶"
    };
    const buttons = [...document.querySelectorAll("button[data-position]")];
    const moveStatus = document.getElementById("move-status");
    const moveStatusText = document.getElementById("move-status-text");
    const currentStatus = document.getElementById("current-status");
    const currentStatusText = document.getElementById("current-status-text");
    const connectionStatus = document.getElementById("connection-status");
    const readyStatus = document.getElementById("ready-status");
    const enableStatus = document.getElementById("enable-status");
    const statusTip = document.getElementById("status-tip");
    const toggleEnableButton = document.getElementById("toggle-enable-button");
    const toggleEnableTitle = toggleEnableButton.querySelector(".button-title");
    const jogButtons = [...document.querySelectorAll(".jog-btn")];
    let latestState = null;
    let isActionBusy = false;
    let isJogging = false;
    let jogTimer = null;

    function setBusy(isBusy) {
      isActionBusy = isBusy;
      buttons.forEach((button) => {
        button.disabled = isBusy;
      });
      if (latestState) {
        updateToggleEnableButton(latestState, isBusy);
        updateJogButtons(latestState, isBusy);
      } else {
        toggleEnableButton.disabled = isBusy;
        jogButtons.forEach((btn) => {
          btn.disabled = true;
        });
      }
    }

    function setJogging(active) {
      isJogging = active;
      if (latestState) {
        updatePositionButtons(latestState, isActionBusy);
        updateToggleEnableButton(latestState, isActionBusy);
        updateJogButtons(latestState, isActionBusy);
      }
    }

    function stopJog() {
      if (jogTimer !== null) {
        window.clearInterval(jogTimer);
        jogTimer = null;
      }
      setJogging(false);
    }

    function updateJogButtons(state, isBusy) {
      const disabled = isBusy || isJogging || !state || !state.ready || !state.enabled;
      jogButtons.forEach((btn) => {
        btn.disabled = disabled;
      });
    }

    function formatJointValues(values) {
      if (!values) {
        return "暂无数据";
      }
      return "[" + values.map((value) => Math.round(value)).join(", ") + "]";
    }

    function setMoveStatus(message, kind) {
      moveStatusText.textContent = message;
      moveStatus.className = "status" + (kind ? " " + kind : "");
    }

    function setCurrentStatus(message, kind) {
      currentStatusText.textContent = message;
      currentStatus.className = "status" + (kind ? " " + kind : "");
    }

    function setPill(element, text, kind) {
      element.textContent = text;
      element.className = "pill" + (kind ? " " + kind : "");
    }

    function updatePositionButtons(state, isBusy) {
      const disabled = isBusy || isJogging || !state || !state.ready || !state.enabled;
      buttons.forEach((button) => {
        button.disabled = disabled;
      });
    }

    function updateToggleEnableButton(state, isBusy) {
      const block = isBusy || isJogging;
      toggleEnableButton.className = "secondary";
      if (!state.connected) {
        toggleEnableButton.classList.add("disabled-state");
        toggleEnableButton.disabled = true;
        toggleEnableTitle.textContent = "未连接";
        return;
      }

      if (!state.ready) {
        toggleEnableButton.classList.add("enable");
        toggleEnableButton.disabled = block;
        toggleEnableTitle.textContent = isBusy ? "初始化中..." : "初始化机械臂";
        return;
      }

      if (!state.enabled) {
        toggleEnableButton.classList.add("enable");
        toggleEnableButton.disabled = block;
        toggleEnableTitle.textContent = isBusy ? "使能中..." : "上使能";
        return;
      }

      if (!state.at_shutdown_prep) {
        toggleEnableButton.classList.add("disabled-state");
        toggleEnableButton.disabled = true;
        toggleEnableTitle.textContent = "下使能";
      } else {
        toggleEnableButton.classList.add("disable");
        toggleEnableButton.disabled = block;
        toggleEnableTitle.textContent = isBusy ? "下使能中..." : "下使能";
      }
    }

    function renderState(state) {
      latestState = state;
      setPill(connectionStatus, state.connected ? "已连接" : "未连接", state.connected ? "ok" : "err");
      setPill(readyStatus, state.ready ? "已准备" : "未准备", state.ready ? "ok" : "warn");
      setPill(enableStatus, state.enabled ? "已使能" : "未使能", state.enabled ? "ok" : "warn");
      statusTip.textContent = state.summary || "暂无状态说明";
      setCurrentStatus(formatJointValues(state.current_deg), "");
      updatePositionButtons(state, isActionBusy);
      updateToggleEnableButton(state, isActionBusy);
      updateJogButtons(state, isActionBusy);
    }

    async function callAction(url, pendingMessage, successFormatter) {
      setBusy(true);
      setMoveStatus(pendingMessage, "");

      try {
        const response = await fetch(url, { method: "POST" });
        const data = await response.json();
        if (!response.ok || !data.ok) {
          throw new Error(data.message || "未知错误");
        }
        setMoveStatus(successFormatter(data), "ok");
        await refreshStatus();
      } catch (error) {
        setMoveStatus(error.message, "err");
        await refreshStatus();
      } finally {
        setBusy(false);
      }
    }

    async function moveTo(position) {
      const positionLabel = POSITION_LABELS[position] || position;
      await callAction(
        "/api/move/" + encodeURIComponent(position),
        "正在移动到" + positionLabel + "...",
        (data) => "已移动到" + data.position_label
      );
    }

    buttons.forEach((button) => {
      button.addEventListener("click", () => moveTo(button.dataset.position));
    });

    const JOG_INTERVAL_MS = 130;

    async function jogJointTick(joint, direction) {
      try {
        const response = await fetch("/api/jog/joint", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ joint: joint, direction: direction })
        });
        const data = await response.json();
        if (!response.ok || !data.ok) {
          throw new Error(data.message || "关节微调失败");
        }
      } catch (error) {
        stopJog();
        setMoveStatus(error.message, "err");
      }
    }

    function bindJogButton(element, joint, direction) {
      element.addEventListener("pointerdown", (event) => {
        if (element.disabled || event.button !== 0) {
          return;
        }
        event.preventDefault();
        try {
          element.setPointerCapture(event.pointerId);
        } catch (e) {
          /* ignore */
        }
        if (jogTimer !== null) {
          return;
        }
        setJogging(true);
        jogJointTick(joint, direction);
        jogTimer = window.setInterval(() => jogJointTick(joint, direction), JOG_INTERVAL_MS);
      });
      element.addEventListener("pointerup", stopJog);
      element.addEventListener("pointercancel", stopJog);
      element.addEventListener("lostpointercapture", stopJog);
    }

    for (let j = 1; j <= 7; j++) {
      const line = document.querySelector('.jog-line[data-joint="' + j + '"]');
      if (!line) {
        continue;
      }
      bindJogButton(line.querySelector('[data-dir="-1"]'), j, -1);
      bindJogButton(line.querySelector('[data-dir="1"]'), j, 1);
    }
    window.addEventListener("blur", stopJog);

    toggleEnableButton.addEventListener("click", async () => {
      if (!latestState) {
        await refreshStatus();
        if (!latestState) {
          return;
        }
      }
      if (!latestState.ready) {
        if (!latestState.connected) {
          return;
        }
        await callAction(
          "/api/initialize",
          "正在初始化机械臂...",
          () => "机械臂初始化完成，已建立稳定反馈"
        );
        return;
      }
      if (!latestState.enabled) {
        await callAction(
          "/api/enable",
          "正在使能机械臂...",
          () => "机械臂已使能，可以执行移动操作"
        );
        return;
      }
      await callAction(
        "/api/disable",
        "正在下使能...",
        () => "机械臂已下使能，可以安全断电"
      );
    });

    async function refreshStatus() {
      try {
        const response = await fetch("/api/status");
        const data = await response.json();
        if (!response.ok || !data.ok) {
          throw new Error(data.message || "状态读取失败");
        }
        renderState(data);
      } catch (error) {
        setPill(connectionStatus, "异常", "err");
        setPill(readyStatus, "异常", "err");
        setPill(enableStatus, "异常", "err");
        statusTip.textContent = "状态读取失败: " + error.message;
        setCurrentStatus("读取失败: " + error.message, "err");
        updatePositionButtons(null, false);
        jogButtons.forEach((btn) => {
          btn.disabled = true;
        });
        toggleEnableButton.disabled = true;
        toggleEnableButton.className = "secondary";
        toggleEnableButton.classList.add("disabled-state");
        toggleEnableTitle.textContent = "未就绪";
        latestState = null;
        return;
      }
    }

    async function refreshStatusLoop() {
      await refreshStatus();
      window.setTimeout(refreshStatusLoop, 1200);
    }

    refreshStatusLoop();
  </script>
</body>
</html>
"""


POSITION_KEY_ALIASES = {
    "Initial": "初始位置",
    "ShutdownPrep": "断电位置",
    "Ready": "拍摄高位",
    "Work": "拍摄低位",
    "GrabCone": "抓取锥桶",
    "LiftCone": "提取锥桶",
    "PlaceCone": "放下锥桶",
    "Custom1": "抓取锥桶",
    "Custom3": "提取锥桶",
    "Custom4": "放下锥桶",
}


POSITION_LABELS = {
    "初始位置": "初始位置",
    "断电位置": "断电位置",
    "拍摄高位": "拍摄高位",
    "拍摄低位": "拍摄低位",
    "抓取锥桶": "抓取锥桶",
    "提取锥桶": "提取锥桶",
    "放下锥桶": "放下锥桶",
}

SHUTDOWN_POSITION_KEY = "断电位置"

STATUS_PROBE_TIMEOUT = 0.2
SHUTDOWN_PREP_JOINT4_MIN_DEG = 122.0
FEEDBACK_RECOVERY_TIMEOUT = 1.0
FEEDBACK_RECOVERY_COOLDOWN = 3.0


def deadline_from_timeout(timeout: float) -> float | None:
    if timeout <= 0:
        return None
    return time.monotonic() + timeout


def timed_out(deadline: float | None) -> bool:
    return deadline is not None and time.monotonic() >= deadline


def degrees_to_radians(values: list[float]) -> list[float]:
    return [math.radians(value) for value in values]


def radians_to_degrees(values: list[float]) -> list[float]:
    return [round(math.degrees(value), 3) for value in values]


def wait_feedback_ready(robot, timeout: float) -> bool:
    deadline = deadline_from_timeout(timeout)
    while not timed_out(deadline):
        joint_angles = robot.get_joint_angles()
        if joint_angles is not None and getattr(joint_angles, "hz", 0) > 0:
            return True
        time.sleep(0.05)
    return False


def wait_until_enabled(robot, timeout: float) -> bool:
    deadline = deadline_from_timeout(timeout)
    while not timed_out(deadline):
        if robot.enable():
            return True
        robot.set_normal_mode()
        time.sleep(0.05)
    return False


def wait_until_disabled(robot, timeout: float) -> bool:
    deadline = deadline_from_timeout(timeout)
    while not timed_out(deadline):
        if robot.disable():
            return True
        time.sleep(0.05)
    return False


def set_normal_mode_and_settle(robot, settle_time: float = 0.2) -> None:
    robot.set_normal_mode()
    time.sleep(settle_time)


def send_joint_target_stably(
    robot,
    target_rad: list[float],
    repeats: int,
    repeat_interval: float,
    log_prefix: str,
) -> None:
    repeats = max(1, int(repeats))
    repeat_interval = max(0.0, float(repeat_interval))

    for attempt in range(repeats):
        robot.move_j(target_rad)
        if attempt == 0:
            print(f"{log_prefix} move_j command sent")
        else:
            print(f"{log_prefix} move_j command re-sent ({attempt + 1}/{repeats})")
        if attempt + 1 < repeats and repeat_interval > 0.0:
            time.sleep(repeat_interval)


def wait_reached(
    robot,
    target_rad: list[float],
    timeout: float,
    tolerance_deg: float,
    resend_interval: float = 0.0,
    log_prefix: str = "[web_control]",
) -> tuple[bool, list[float] | None, float | None]:
    deadline = deadline_from_timeout(timeout)
    tolerance_rad = math.radians(tolerance_deg)
    stable_hits = 0
    last_joint_values = None
    last_max_error_rad = None
    next_resend_time = time.monotonic() + max(0.0, resend_interval)

    while not timed_out(deadline):
        joint_angles = robot.get_joint_angles()
        if joint_angles is None or len(joint_angles.msg) != len(target_rad):
            time.sleep(0.05)
            continue

        last_joint_values = list(joint_angles.msg)
        max_error = max(abs(current - target) for current, target in zip(joint_angles.msg, target_rad))
        last_max_error_rad = max_error
        if max_error <= tolerance_rad:
            stable_hits += 1
            if stable_hits >= 5:
                return True, last_joint_values, last_max_error_rad
        else:
            stable_hits = 0
            if resend_interval > 0.0 and time.monotonic() >= next_resend_time:
                robot.move_j(target_rad)
                print(f"{log_prefix} refreshing move_j target")
                next_resend_time = time.monotonic() + resend_interval
        time.sleep(0.1)
    return False, last_joint_values, last_max_error_rad


def firmware_constant(name: str):
    mapping = {
        "default": NeroFW.DEFAULT,
        "v111": NeroFW.V111,
    }
    if name not in mapping:
        raise ValueError(f"不支持的固件版本: {name}")
    return mapping[name]


def load_config() -> dict:
    config_path = WEB_CONTROL_DIR / "config.json"
    with config_path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)

    positions_deg = dict(config.get("positions_deg", {}))
    for old_key, new_key in POSITION_KEY_ALIASES.items():
        if old_key in positions_deg and new_key not in positions_deg:
            positions_deg[new_key] = positions_deg[old_key]
        positions_deg.pop(old_key, None)

    config["positions_deg"] = positions_deg
    return config


class NeroController:
    def __init__(self, config: dict):
        self._config = config
        self._robot = None
        self._lock = threading.Lock()
        self._last_feedback_recovery_attempt = 0.0

    def _build_robot(self):
        robot_cfg = create_agx_arm_config(
            robot=ArmModel.NERO,
            firmeware_version=firmware_constant(self._config["firmware_version"]),
            interface="socketcan",
            channel=self._config["can_port"],
        )
        return AgxArmFactory.create_arm(robot_cfg)

    def _ensure_robot_connected(self):
        if self._robot is None or not self._robot.is_connected():
            self._robot = self._build_robot()
            self._robot.connect()
        return self._robot

    def _ensure_feedback_ready(self, timeout: float):
        robot = self._ensure_robot_connected()
        if not wait_feedback_ready(robot, timeout):
            raise RuntimeError("等待机械臂反馈超时，请确认 CAN 已激活且机械臂已上电")
        return robot

    def _maybe_recover_feedback(self, robot) -> bool:
        now = time.monotonic()
        if now - self._last_feedback_recovery_attempt < FEEDBACK_RECOVERY_COOLDOWN:
            return False

        self._last_feedback_recovery_attempt = now
        print("[web_control] no feedback yet, sending set_normal_mode to enable CAN push")
        try:
            set_normal_mode_and_settle(robot, 0.1)
        except Exception as exc:
            print(f"[web_control] feedback recovery failed: {exc}")
            return False
        return wait_feedback_ready(robot, FEEDBACK_RECOVERY_TIMEOUT)

    def _wait_feedback_after_normal_mode(self, robot, timeout: float) -> bool:
        set_normal_mode_and_settle(robot)
        if wait_feedback_ready(robot, timeout):
            return True
        return self._maybe_recover_feedback(robot)

    def _restore_feedback_without_enable(self, robot, timeout: float) -> bool:
        print("[web_control] trying to restore CAN feedback before re-enabling")
        return self._wait_feedback_after_normal_mode(robot, timeout)

    def _get_current_joint_degrees(self, robot) -> list[float] | None:
        joint_angles = robot.get_joint_angles()
        if joint_angles is None:
            return None
        return radians_to_degrees(list(joint_angles.msg))

    def _is_enabled(self, robot) -> bool:
        return bool(robot.get_joint_enable_status(255))

    def _is_at_position(self, current_deg: list[float] | None, target_deg: list[float], tolerance_deg: float) -> bool:
        if current_deg is None or len(current_deg) != len(target_deg):
            return False
        return all(abs(current - target) <= tolerance_deg for current, target in zip(current_deg, target_deg))

    def _is_at_shutdown_prep_position(self, current_deg: list[float] | None, target_deg: list[float]) -> bool:
        if current_deg is None or len(current_deg) != len(target_deg):
            return False

        tolerance_deg = self._config["tolerance_deg"]
        for index, (current, target) in enumerate(zip(current_deg, target_deg)):
            if index == 3:
                if current < SHUTDOWN_PREP_JOINT4_MIN_DEG:
                    return False
                continue
            if abs(current - target) > tolerance_deg:
                return False
        return True

    def get_status(self, positions_deg: dict[str, list[float]]) -> dict:
        shutdown_target = positions_deg[SHUTDOWN_POSITION_KEY]

        with self._lock:
            connected = False
            ready = False
            enabled = False
            current_deg = None
            summary = "机械臂未连接"

            try:
                robot = self._ensure_robot_connected()
                connected = robot.is_connected()
                ready = wait_feedback_ready(robot, STATUS_PROBE_TIMEOUT)
                if ready:
                    current_deg = self._get_current_joint_degrees(robot)
                    enabled = self._is_enabled(robot)
                    summary = "机械臂已准备好" if enabled else "机械臂已准备好，等待使能"
                else:
                    summary = (
                        "已连接 CAN，但尚未收到稳定关节反馈。"
                        "请点击“初始化机械臂”完成使能和 normal mode 初始化。"
                        if connected
                        else "机械臂未连接"
                    )
            except Exception as exc:
                summary = f"状态读取异常: {exc}"

            at_shutdown_prep = self._is_at_shutdown_prep_position(
                current_deg,
                shutdown_target,
            )

            if ready and enabled and not at_shutdown_prep:
                summary = "机械臂已使能，下使能请先回到断电位置"
            elif ready and enabled and at_shutdown_prep:
                summary = "机械臂已使能，且已在断电位置"

            return {
                "ok": True,
                "connected": connected,
                "ready": ready,
                "enabled": enabled,
                "current_deg": current_deg,
                "at_shutdown_prep": at_shutdown_prep,
                "summary": summary,
            }

    def initialize_arm(self) -> dict:
        with self._lock:
            robot = self._ensure_robot_connected()

            if wait_feedback_ready(robot, STATUS_PROBE_TIMEOUT):
                current_deg = self._get_current_joint_degrees(robot)
                return {
                    "message": "机械臂反馈已就绪",
                    "current_deg": current_deg,
                }

            feedback_recovery_timeout = min(
                self._config["feedback_timeout"],
                FEEDBACK_RECOVERY_TIMEOUT + 0.5,
            )
            if self._restore_feedback_without_enable(robot, feedback_recovery_timeout):
                robot.set_speed_percent(self._config["speed_percent"])
                current_deg = self._get_current_joint_degrees(robot)
                return {
                    "message": "机械臂初始化成功，已恢复稳定反馈",
                    "current_deg": current_deg,
                }

            if not wait_until_enabled(robot, self._config["enable_timeout"]):
                raise RuntimeError("机械臂初始化失败：使能超时，请确认机械臂已上电且状态灯正常")

            if not self._wait_feedback_after_normal_mode(robot, self._config["feedback_timeout"]):
                raise RuntimeError("机械臂已使能，但未收到稳定关节反馈，请稍后重试")

            robot.set_speed_percent(self._config["speed_percent"])
            current_deg = self._get_current_joint_degrees(robot)
            return {
                "message": "机械臂初始化成功，已建立稳定反馈",
                "current_deg": current_deg,
            }

    def enable_arm(self) -> dict:
        with self._lock:
            robot = self._ensure_feedback_ready(self._config["feedback_timeout"])
            if self._is_enabled(robot):
                current_deg = self._get_current_joint_degrees(robot)
                return {
                    "message": "机械臂已经处于使能状态",
                    "current_deg": current_deg,
                }

            if not wait_until_enabled(robot, self._config["enable_timeout"]):
                raise RuntimeError("机械臂使能失败，请重试")

            set_normal_mode_and_settle(robot)
            robot.set_speed_percent(self._config["speed_percent"])
            current_deg = self._get_current_joint_degrees(robot)
            return {
                "message": "机械臂使能成功",
                "current_deg": current_deg,
            }

    def disable_arm(self, positions_deg: dict[str, list[float]]) -> dict:
        shutdown_target = positions_deg[SHUTDOWN_POSITION_KEY]

        with self._lock:
            robot = self._ensure_feedback_ready(self._config["feedback_timeout"])
            current_deg = self._get_current_joint_degrees(robot)

            if not self._is_enabled(robot):
                return {
                    "message": "机械臂已经处于下使能状态",
                    "current_deg": current_deg,
                }

            if not self._is_at_shutdown_prep_position(current_deg, shutdown_target):
                raise RuntimeError("请先回到断电位置")

            if not wait_until_disabled(robot, self._config["enable_timeout"]):
                raise RuntimeError("机械臂下使能失败，请重试")

            return {
                "message": "机械臂已下使能",
                "current_deg": self._get_current_joint_degrees(robot),
            }

    def move_to(self, name: str, positions_deg: dict[str, list[float]]) -> dict:
        if name not in positions_deg:
            raise KeyError(f"未知位置: {name}")

        target_deg = positions_deg[name]
        target_rad = degrees_to_radians(target_deg)

        with self._lock:
            robot = self._ensure_feedback_ready(self._config["feedback_timeout"])
            if not self._is_enabled(robot):
                raise RuntimeError("请先使能机械臂")

            set_normal_mode_and_settle(robot)
            robot.set_speed_percent(self._config["speed_percent"])
            current_before = robot.get_joint_angles()
            current_before_deg = (
                radians_to_degrees(list(current_before.msg))
                if current_before is not None
                else None
            )
            print(
                f"[web_control] move request={name} "
                f"current_before_deg={current_before_deg} "
                f"target_deg={target_deg}"
            )
            send_joint_target_stably(
                robot,
                target_rad,
                self._config.get("command_repeats", 3),
                self._config.get("command_repeat_interval", 0.08),
                "[web_control]",
            )
            reached, current_rad, max_error_rad = wait_reached(
                robot,
                target_rad,
                self._config["reach_timeout"],
                self._config["tolerance_deg"],
                self._config.get("command_refresh_interval", 1.0),
                "[web_control]",
            )
            if not reached:
                current_deg = radians_to_degrees(current_rad) if current_rad is not None else None
                max_error_deg = round(math.degrees(max_error_rad), 3) if max_error_rad is not None else None
                raise RuntimeError(
                    f"机械臂在超时前未到达{POSITION_LABELS.get(name, name)}"
                    f"当前关节角度(deg): {current_deg}，最大误差(deg): {max_error_deg}"
                )

            current_after = robot.get_joint_angles()
            current_after_deg = (
                radians_to_degrees(list(current_after.msg))
                if current_after is not None
                else None
            )
            print(
                f"[web_control] move done={name} "
                f"current_after_deg={current_after_deg}"
            )

        return {
            "position_name": name,
            "position_label": POSITION_LABELS.get(name, name),
            "target_deg": target_deg,
            "current_deg": current_after_deg,
            "message": f"已移动到{POSITION_LABELS.get(name, name)}",
        }

    def jog_joint(self, joint_one_based: int, direction: int) -> dict:
        if joint_one_based < 1 or joint_one_based > 7:
            raise ValueError("joint 必须在 1–7 之间")
        if direction not in (-1, 1):
            raise ValueError("direction 必须为 1 或 -1")

        joint_index = joint_one_based - 1
        step_deg = float(self._config.get("jog_step_deg", 1.5))
        cmd_repeats = int(self._config.get("command_repeats", 3))
        jog_repeats = max(1, min(2, cmd_repeats))

        with self._lock:
            robot = self._ensure_feedback_ready(self._config["feedback_timeout"])
            if not self._is_enabled(robot):
                raise RuntimeError("请先使能机械臂")

            set_normal_mode_and_settle(robot, 0.05)
            robot.set_speed_percent(self._config["speed_percent"])
            current_deg = self._get_current_joint_degrees(robot)
            if current_deg is None or len(current_deg) <= joint_index:
                raise RuntimeError("无法读取关节角度")

            target_deg = list(current_deg)
            target_deg[joint_index] += direction * step_deg
            target_rad = degrees_to_radians(target_deg)
            send_joint_target_stably(
                robot,
                target_rad,
                jog_repeats,
                self._config.get("command_repeat_interval", 0.08),
                "[web_control_jog]",
            )

        return {
            "message": f"关节{joint_one_based}微调",
            "joint": joint_one_based,
            "direction": direction,
            "step_deg": step_deg,
            "target_deg": target_deg,
        }

    def close(self):
        if self._robot is None:
            return
        try:
            self._robot.disconnect()
        finally:
            self._robot = None


class WebHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, controller: NeroController, positions_deg: dict[str, list[float]], **kwargs):
        self.controller = controller
        self.positions_deg = positions_deg
        super().__init__(*args, **kwargs)

    def log_message(self, format, *args):
        print(f"[web_control] {self.address_string()} - {format % args}")

    def _read_json_body(self) -> dict:
        length_raw = self.headers.get("Content-Length")
        try:
            length = int(length_raw or "0")
        except ValueError:
            length = 0
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def _send_json(self, status_code: int, payload: dict):
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_html(self, html: str):
        encoded = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_html(HTML_PAGE)
            return
        if parsed.path == "/api/positions":
            self._send_json(
                HTTPStatus.OK,
                {"ok": True, "positions_deg": self.positions_deg},
            )
            return
        if parsed.path == "/api/status":
            try:
                payload = self.controller.get_status(self.positions_deg)
            except Exception as exc:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "message": str(exc)})
            else:
                self._send_json(HTTPStatus.OK, payload)
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "message": "未找到接口"})

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/initialize":
            try:
                result = self.controller.initialize_arm()
            except RuntimeError as exc:
                self._send_json(HTTPStatus.CONFLICT, {"ok": False, "message": str(exc)})
            except Exception as exc:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "message": str(exc)})
            else:
                self._send_json(HTTPStatus.OK, {"ok": True, **result})
            return
        if parsed.path == "/api/enable":
            try:
                result = self.controller.enable_arm()
            except Exception as exc:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "message": str(exc)})
            else:
                self._send_json(HTTPStatus.OK, {"ok": True, **result})
            return
        if parsed.path == "/api/disable":
            try:
                result = self.controller.disable_arm(self.positions_deg)
            except RuntimeError as exc:
                self._send_json(HTTPStatus.CONFLICT, {"ok": False, "message": str(exc)})
            except Exception as exc:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "message": str(exc)})
            else:
                self._send_json(HTTPStatus.OK, {"ok": True, **result})
            return
        if parsed.path == "/api/jog/joint":
            body = self._read_json_body()
            try:
                joint = int(body.get("joint", 0))
                direction = int(body.get("direction", 0))
                result = self.controller.jog_joint(joint, direction)
            except ValueError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "message": str(exc)})
            except RuntimeError as exc:
                self._send_json(HTTPStatus.CONFLICT, {"ok": False, "message": str(exc)})
            except Exception as exc:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "message": str(exc)})
            else:
                self._send_json(HTTPStatus.OK, {"ok": True, **result})
            return
        if parsed.path.startswith("/api/move/"):
            position_name = unquote(parsed.path.rsplit("/", 1)[-1])
            try:
                result = self.controller.move_to(position_name, self.positions_deg)
            except KeyError as exc:
                self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "message": str(exc)})
            except RuntimeError as exc:
                self._send_json(HTTPStatus.CONFLICT, {"ok": False, "message": str(exc)})
            except Exception as exc:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "message": str(exc)})
            else:
                self._send_json(HTTPStatus.OK, {"ok": True, **result})
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "message": "未找到接口"})


def main():
    config = load_config()
    server_cfg = config["server"]
    robot_cfg = config["robot"]
    positions_deg = config["positions_deg"]
    controller = NeroController(robot_cfg)

    handler = partial(
        WebHandler,
        controller=controller,
        positions_deg=positions_deg,
    )
    httpd = ThreadingHTTPServer((server_cfg["host"], server_cfg["port"]), handler)

    print("[web_control] protocol: http")
    print(f"[web_control] bind address: http://{server_cfg['host']}:{server_cfg['port']}")
    print(f"[web_control] can port: {robot_cfg['can_port']}")
    print(f"[web_control] positions: {', '.join(positions_deg.keys())}")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("[web_control] stopping")
    finally:
        httpd.server_close()
        controller.close()


if __name__ == "__main__":
    main()
