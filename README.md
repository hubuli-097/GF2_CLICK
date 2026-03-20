# GF2 自动点击助手

少女前线 2：追放 的咖啡厅订单自动点击小工具，通过图像模板匹配识别订单区域并自动点击配料与提交。

## 功能特点

- **自动识别**：基于 OpenCV 模板匹配，识别订单区域内的配料图标
- **自动补充**：命中主配料后自动点击对应补充按钮
- **自动提交**：一轮点击完成后自动提交订单
- **窗口锁定**：自动查找游戏窗口（标题含「少女前线2」或「GF2_Exilium」），仅截取该窗口
- **GUI 界面**：支持启动/停止，实时查看运行日志

## 系统要求

- **操作系统**：Windows 10 及以上（64 位）
- **权限**：**须以管理员身份运行**。游戏以管理员运行时，本程序也必须以管理员运行才能正常点击；启动时会自动请求提升权限
- **前置**：需先打开游戏并进入咖啡厅订单界面
- **标定分辨率**：当前内置坐标与模板基于 **1600×900** 游戏分辨率标定；分辨率或 DPI 缩放不同时需自行重新标定

## 快速开始

### 方式一：使用打包好的 exe（推荐）

1. 下载 `GF2_点击助手.exe`（在 [Releases](https://github.com/chenruiqi048-cmd/GF2_CLICK/releases) 中获取，或本地打包见下方说明）
2. 确保 `calib` 和 `click_shots` 文件夹与 exe 同目录，或使用已内嵌资源的单文件 exe
3. 双击运行，点击「启动」即可

### 方式二：从源码运行

1. 安装 Python 3.8+
2. 克隆项目并安装依赖：
   ```bash
   git clone https://github.com/chenruiqi048-cmd/GF2_CLICK.git
   cd GF2_CLICK
   pip install -r requirements.txt
   ```
3. 运行 GUI 版本：
   ```bash
   python gf2_gui.py
   ```
4. 或运行命令行版本：
   ```bash
   python gf2_bot.py
   ```
   （按 Ctrl+C 停止）

## 目录结构

```
GF2_CLICK/
├── gf2_bot.py       # 核心逻辑
├── gf2_gui.py       # GUI 入口
├── calib/
│   └── points.json  # 坐标标定文件（需与本机分辨率匹配）
├── click_shots/     # 模板图片（配料图标、提交按钮等）
├── requirements.txt
├── start_bot.bat    # 一键启动脚本（使用 venv 时）
└── README.md
```

## 自定义标定

若你的分辨率或游戏窗口布局与默认不同，需要重新标定坐标：

1. 使用项目内的 `capture_points.py` 或 `capture_coords_only.py` 采集坐标
2. 在 `click_shots` 目录下放置对应的模板截图
3. 确保 `calib/points.json` 中的点位与模板文件名对应

## 打包为 exe

```bash
pip install pyinstaller
pyinstaller build.spec
```

或使用命令行：

```bash
pyinstaller --onefile --windowed --add-data "calib;calib" --add-data "click_shots;click_shots" --name "GF2_Click_Helper" gf2_gui.py
```

生成的 exe 位于 `dist/` 目录（约 60MB）。

## 封号与风险说明

本工具属于**纯外部辅助**：不读写游戏进程内存、不注入 DLL，只在系统层面模拟鼠标点击与读取屏幕画面（截图）。与内挂、修改器等相比，从技术路径上**通常风险较低**，请自行权衡。

**结论**：使用本工具所带来的账号后果由使用者自行承担；若介意风险，请勿使用或仅小号尝试。具体内容以游戏官方用户协议及最新运营公告为准。

## 注意事项

- 本工具仅供学习与辅助使用，请遵守游戏相关条款
- 坐标与模板基于 **1600×900** 分辨率标定，游戏窗口该尺寸不受 Windows DPI 缩放影响；更换分辨率后需重新标定
- 部分杀毒软件可能误报，可添加信任或排除目录

## 许可证

MIT License
