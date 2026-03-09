# Monitor Insight

一个基于 PyQt6 的 Windows 桌面工具，用来识别当前电脑连接的显示器信息，并在显示器支持 DDC/CI 时读取和切换输入信号。

## 是否需要安装 Python / PyQt

不需要。

当前项目已经使用 PyInstaller 打包，发布给其他电脑时，不需要额外安装 Python、PyQt6 或你的源码环境。
只要目标机器是 64 位 Windows 10 / 11，一般就可以直接运行。

## 推荐发布方式

提供两种发布形态：

- 单文件版：只有一个 `MonitorInsight.exe`，分发方便
- 便携版：一个完整文件夹，兼容性通常比单文件版更稳，推荐发给刚装好系统的电脑使用

优先建议使用便携版，因为它把运行时 DLL 和 Qt 插件直接展开在 EXE 旁边，遇到安全软件、临时目录权限、首次解包失败这类问题的概率更低。

## 功能

- 自动识别当前已连接显示器
- 显示厂商、型号、序列号
- 显示桌面分辨率、估算原生分辨率、刷新率
- 显示系统缩放比例、DPI、物理尺寸、对角线
- 显示当前信号源，例如 HDMI 1、HDMI 2、DisplayPort 1
- 读取显示器声明支持的信号源列表
- 在支持 DDC/CI 的显示器上切换信号源
- 支持导出 JSON 报告

## 注意事项

- 信号源读取和切换依赖显示器开启 DDC/CI
- 不是所有显示器都会返回完整的信号源列表
- 切换到没有有效信号的端口后，显示器可能会短暂黑屏，需要手动切回
- 目前发布目标是 64 位 Windows 桌面系统

## 源码运行

```powershell
.\PythonEnv\.venv311\Scripts\python.exe .\MonitorInsightProject\main.py
```

只输出 JSON：

```powershell
.\PythonEnv\.venv311\Scripts\python.exe .\MonitorInsightProject\main.py --json
```

## 构建发布包

只构建单文件版：

```powershell
.\MonitorInsightProject\build_exe.cmd
```

构建完整发布包：

```powershell
.\MonitorInsightProject\build_release.cmd
```

构建完成后，发布文件会在：

- `MonitorInsightProject\release\OneFile\MonitorInsight.exe`
- `MonitorInsightProject\release\Portable\MonitorInsightPortable\MonitorInsight.exe`
- `MonitorInsightProject\release\MonitorInsight_OneFile.zip`
- `MonitorInsightProject\release\MonitorInsight_Portable.zip`
