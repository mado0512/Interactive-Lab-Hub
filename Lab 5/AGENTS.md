# AGENTS.md

## 语言偏好

- **默认用简体中文和我交流。** 代码、命令、变量名、日志和文件内容保持英文。
- 技术术语可以保留英文原文（如 PipeWire、dBFS、PULSE_SOURCE）。

## 项目背景：Lab 5 「Overnight Sensation」

这是 **Interactive Lab Hub** 的第 5 个 Lab（Observant Systems），作者 Shifeng Hong (sh2769) 与 Jessica Chon。
主题是**观察型系统（observant systems）**：一个能感知环境事件并在睡眠期间自主记录、醒来后给出反馈的装置。

核心约束：**AI 全部跑在 Pi 上，离线运行**。Pi 5 上运行 YOLO 做「看」、Qwen 做「想」，模型很慢，但有一整晚的时间。

### 三段式夜间交互

1. **睡前交接（Part F/G）**：人把夜晚交给设备——按下 Lab 4 的按钮或说一句 "good night"（Lab 3 麦克风）。
   设备在 30 秒内确认：OLED / Mini PiTFT 上显示一行字，LED 变暗而不是变亮，然后 `overnight.py` 开始写 `night_log.jsonl`。
2. **睡眠中观察（Part H）**：每 5 秒采样一次音频（响度 + 低频能量，鼾声基频约 60–300 Hz），
   每 10–20 秒取一帧做 MediaPipe Face Mesh 的嘴部开合度（MAR ≈0.0 闭合，≈0.3–0.6 张开）和 YOLO 的
   在床/仰卧/侧卧判断。每行日志刻意平淡：`03:12:20 snore_event 6s, mouth_open 0.41, person supine`。
3. **醒来揭示（Part I）**：再按一次按钮，Qwen 生成三句话报告，通过 Lab 3 的扬声器朗读，并显示在屏幕上。
   必须对「什么都没发生的一夜」诚实，说 *possible snoring*，**绝不诊断呼吸暂停**。

### 技术栈与已有模块

| 文件 | 作用 |
|---|---|
| `yolo_to_qwen.py` | Part E：YOLO + `interpret()` 把画面翻译成文字，再交给 Qwen |
| `overnight.py` | Part H：夜间值守，每 `--interval` 秒记录一次，只感知不推理 |
| `morning.py` | Part I：读日志，让 Qwen 写三句晨间报告 |
| `mouth_open.py` | MediaPipe Face Mesh 计算嘴部开合度 |
| `snore_monitor.py` | **音频侧**：麦克风监听，超阈值把鼾声录成 WAV；内含可复用的 `SnoreMachine` |
| `night_watch.py` | **合并版**：音频 + 嘴部，一个 TUI、一个 `night_log.jsonl` |
| `README.md` | 实验报告全文：设计思路、Part E 的两次对比、修订后的故事板 |
| `legacy/` | 旧版工具（MobileNet、Teachable Machine、Moondream、音频分析等），可选 |

### 隐私红线（README 明确承诺，不要违反）

- 摄像头只对准**枕头和枕头上的人**，不对准门口、床的其余部分或房间。
- **不保存画面**：取完数字就丢弃帧，快照不离开 Pi，演示后删除。
- 只在自己独居的房间运行；只要房间里有别人就取消这次记录。
- 只能输出「可能的鼾声事件」，不能做任何医学诊断。

## 运行环境

- Raspberry Pi 5，Debian 12 (bookworm)，aarch64，内核 6.12。
- Python 3.12，依赖由 `uv` 管理（`pyproject.toml` + `uv.lock`），`python3` 指向 `.venv`。
- 已装：`ultralytics`、`mediapipe`、`opencv-python`、`sounddevice`、`numpy`、`requests`、`ncnn`。
- Ollama 在本机 `localhost:11434`，默认模型 `qwen3.5:0.8b`。
- 音频由 **PipeWire 1.2.7**（PulseAudio 兼容层）管理。

### 音频实测结论（踩过的坑，别再踩）

- 有两块 USB 采集设备：`card 2` 是摄像头自带麦克风，`card 3` 是 **USB PnP Sound Device**（真正的 USB 麦克风）。
- **不要用 `hw:` 直接打开采集设备**：PipeWire 持有设备，直接访问会丢 6–20% 的音频块。
  正确做法是用 `sounddevice` 的 `pulse` 设备，并用 `PULSE_SOURCE` 环境变量指定麦克风 → 实测 0 丢帧。
- 采样率必须探测：USB PnP 麦克风支持 44100/48000，**不支持 16000**；摄像头麦克风反之。
- 房间本底噪声约 **-42 dBFS**，声音都是相对这个基线来判定的（dBFS 不是声压级 SPL）。
- 用 `arecord` / `pactl` / `--list` 可以快速确认设备与路由。
- **设备索引会变**（实测 pulse 从 3 变成过 2），代码里永远按名字查，不要写死索引。
- `systemctl --user restart pipewire` 会让正在录音的流断掉；`snore_monitor.py` 的看门狗会在
  `--stall-timeout` 后重开，并往日志写 `{"event": "restart"}`。
- 48 kHz 单声道 16 bit ≈ **96 KB/s ≈ 345 MB/小时**，连续录 8 小时约 3 GB。
- **这台 Pi 没有装 `tmux`/`screen`**（README 却让你用 tmux 过夜）：先 `sudo apt install tmux`，
  或者直接用 `nohup ... &`。别以为 `tmux` 存在。

## 代码约定

- 每个工具是**单文件脚本**：模块 docstring 写清用法示例和「为什么这样设计」，用 `argparse`，
  `print(..., flush=True)` 保证重定向到日志时也有输出。
- 长时间运行要能 headless：`tmux new -s night` 或 `nohup ... >> log 2>&1 &`。
- 日志统一用 **JSONL**（一行一个 JSON 对象），便于 `morning.py` 之类的下游脚本直接读。
- 遵循 README 的「采样而非流式」原则（一次看 5–30 秒够用，Pi 不发热）。
- 名字要说得准：`interpret()` 产出的词就是模型世界的全部，YOLO 认不出的东西对 Qwen 来说不存在。

## night_watch.py：两个传感器合成一个界面

- **麦克风是连续的，摄像头是采样的**。声音不能丢（鼾声只有几百毫秒），所以音频走实时回调；
  嘴唇张开是分钟级的状态，所以每 `--cam-interval`（默认 10 秒）取一帧就够——这就是 README
  的「采样而非流式」。摄像头跑在独立线程，主循环从不为了等一帧而阻塞音频。
- **判断逻辑只有一份**：`snore_monitor.SnoreMachine` 把「音频块进、片段出」封装好，
  `snore_monitor.py` 和 `night_watch.py` 都调它，避免两个工具的判断标准慢慢跑偏。
- **日志只有一份**：`night_log.jsonl`，每行都有 `t` 和 `reading`，`morning.py` 直接能读。
  音频片段结束时会把最近的嘴部读数写进去，就是 README 要的 `snore_event 6s, mouth_open 0.41`。
- **不存画面**：帧只被缩成一个数字（MAR）就丢掉，所以离开进程的是 0.41，不是照片。
- 摄像头打不开/拔掉不会拖垮音频：面板显示错误并每 30 秒重试。
- **三种「看不见」必须分开写**，否则早上的报告会编故事：
  `user_leave`（相机正常、画面里没脸 → 人起来了）、`camera_unknown`（相机自身坏了，
  我们无法判断人在不在）、`camera_off`（`--no-camera`）。面板显示成 `USER LEAVE` /
  `UNKNOWN` / `OFF`，日志里是 `user_leave for 6m`、`camera_unknown for 8h`。
- 旧词 `nobody` 只剩 `mouth_open.py` / `overnight.py` 在用；`night_watch.py` 说 `user_leave`，
  两套词汇混写进同一个 `night_log.jsonl` 时要注意。
- 按键：`q` 退出、`m` 立刻存一段、`c` 立刻看一次摄像头。
- **预览窗口**（`--preview` / `--no-preview`，有 X 时默认开）：画面上直接叠声音电平、MAR、
  REC 状态和唇部标记点。窗口打开时摄像头变成连续流、每帧都测（数字才对得上画面）；
  `--no-preview` 才恢复「每 `--cam-interval` 采一帧」。**过夜跑请关掉窗口。**

两个踩过的坑，改这块时不要再踩：

1. **OpenCV 窗口必须在主线程画。** 在工作线程里 `imshow` 不报错，但窗口永远不出现。
   所以摄像头线程只负责采集，主循环负责 `imshow`/`waitKey`/`destroyAllWindows`。
2. 窗口标题是随时刷新的电平字符串，**别用它来找窗口**；用 `xwininfo -root -tree` 确认。
   另外这台机器的桌面是 Wayland（labwc + wayvnc），`ffmpeg -f x11grab` 抓 :0 根窗口是全黑的，
   要截图请用 `import -window <id>`。

注意：**MAR 不是鼾声的证据**。张嘴睡觉很常见，闭着嘴也能打鼾。两个传感器只能一起说
「可能」在打鼾；诊断呼吸暂停需要气流和血氧传感器，这个系统看不到。

## snore_monitor.py 的界面

两套显示，同一个引擎：

- **curses 面板**（默认，仅当 stdout 是终端）：电平条 + 阈值标线、录音中时长、峰值、
  本次会话统计、最近 8 条事件。按键只有 `q`（退出，正在录的段会保存）和 `m`（立刻保存一段）。
- **纯文本行**（重定向到文件、`-v`、`-q`、`--no-tui`）：无转义序列，nohup 日志可读。

电平条刻度是 **-70 .. -6 dBFS**（不是 -120..0），每格约 2 dB，阈值用 `|` 标在条上。
改界面时注意两点踩过的坑：面板每行必须**补齐到全宽**（新事件插到顶部会让文字整体下移，
短行不补齐会残留）；事件行在纯文本模式下要先发 `\r\033[K` 清行，否则会粘在电平表后面。

验证面板不必开真终端：把 `snore_monitor.curses` 换成假对象，用内存网格断言 `addstr` 的内容即可
（比写 ANSI 解释器可靠，ncurses 会发 `ICH`/`DCH`/`SU` 这类优化序列）。

## 待办

- `snore_monitor.py` 主体完成并通过实测（触发、预录、合并、日志、信号处理均正常）。
- `--low-band` 低频门限已用合成信号单元测试验证：180 Hz → 1.000（放行）、3 kHz → 0.000（拒绝）、
  白噪声 → 0.039（拒绝）。注意用扬声器做端到端测试不可靠，它对 180 Hz 的还原只有约 -37 dBFS。
- 过夜能力已实测（150 秒强制连续录音）：RSS 恒定 60 MB、FD 恒定 15、CPU < 2%。
  断流看门狗经过真实 `systemctl --user restart pipewire` 验证可恢复；磁盘保护已验证会拒绝录制并写日志。
- 下一步可做：把 `snore_monitor.py` 接到 `overnight.py` 的 `night_log.jsonl` 格式里，
  让 `morning.py` 能一起读音频事件和视觉事件。
- 还想要但没做：**节律检测**。目前是「响度触发」，说话/关门/狗叫也会录。
  鼾声的真正特征是周期性（呼吸周期 2–6 s、爆发 0.2–0.5 s），
  应对低频能量包络做自相关，要求至少 3 个连续节律爆发达标才算 snore event。
