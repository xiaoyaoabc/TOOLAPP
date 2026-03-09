import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import fitz

ROOT_DIR = Path(__file__).resolve().parent
PDF_DIR = ROOT_DIR / "PDF"
DATA_DIR = ROOT_DIR / "data"
LIBRARY_PATH = DATA_DIR / "chip_library.json"
LIBRARY_SCHEMA_VERSION = 8


def _first_pdf(pattern: str, default_name: str) -> Path:
    matches = sorted(PDF_DIR.glob(pattern))
    return matches[0] if matches else PDF_DIR / default_name

IT5570_PDF = PDF_DIR / "IT5570_C_V0.3.3_20180717.pdf"
IT8613_PDF = PDF_DIR / "IT8613_E_V0.3_20160628.pdf"
IT8625_PDF = PDF_DIR / "IT8625_L_V0.9.2.1_20190604.pdf"
IT8728_PDF = PDF_DIR / "IT8728_F_V0.5_120611.pdf"
IT8772_PDF = PDF_DIR / "IT8772_F_V0.4_031612.pdf"
IT8786_PDF = PDF_DIR / "IT8786_H_V0.7.2_industrial_20190328.pdf"
ASM1061_PDF = PDF_DIR / "Asmedia ASM1061 System BIOS Programming Note V4.2.pdf"
AMD_57396_PDF = PDF_DIR / "57396-A0_3.10.pdf"
MS8510_PDF = _first_pdf("*MS8510*.pdf", "MS8510.pdf")
BQ25720_PDF = _first_pdf("*bq25720*.pdf", "bq25720.pdf")
CW2217_PDF = _first_pdf("*CW2217*.pdf", "CW2217.pdf")
CT7432_PDF = _first_pdf("*CT7432*.pdf", "CT7432.pdf")
IT5570_TOP_VIEW_PAGE = 40
PIN_DESCRIPTION_PAGES = range(45, 52)
GPIO_ALT_PAGES = range(299, 304)
IT8613_PIN_TABLE_PAGE = 24
IT8613_PIN_DESCRIPTION_TABLE_PAGES = range(25, 37)
IT8613_GPIO_ALT_TABLE_PAGES = range(39, 41)
IT8613_GPIO_REG_TABLE_PAGE = 41
ASM1061_CONTENTS_PAGE = 3
AMD_IOMUX_TABLE_PAGES = range(3833, 3843)
AMD_GPIO_BANK_PAGES = range(3882, 3887)
MS8510_TOP_VIEW_PAGE = 13
MS8510_PIN_DESCRIPTION_PAGES = range(14, 21)
ITE_SUPERIO_CONFIGS = {
    "it8625_l": {
        "chip_id": "it8625_l",
        "vendor": "ITE",
        "model": "IT8625E V0.9.2.1",
        "display_name": "IT8625E / IT8625L",
        "category": "Super I/O / HWM",
        "family": "IT8625",
        "series": "IT86xx",
        "chip_role": "Super I/O Controller",
        "variants": ["IT8625E", "IT8625L"],
        "package": "LQFP-128",
        "package_type": "LQFP",
        "document_type": "Datasheet",
        "description": "ITE IT8625 Super I/O 芯片封装图，包含 128 引脚定义、Pin Description、GPIO 复用条件和主要硬件监控/平台控制信号。",
        "features": [
            "支持查看 128 引脚封装和 Pin Description 章节",
            "支持显示 GPIO 复用条件、组别、位号和寄存器控制属性",
            "支持按模块、信号、引脚快速筛选并定位到封装图",
        ],
        "pin_table_page": 26,
        "pin_description_pages": range(27, 48),
        "gpio_alt_pages": range(49, 54),
        "gpio_reg_pages": range(54, 55),
        "pin_count": 128,
    },
    "it8728_f": {
        "chip_id": "it8728_f",
        "vendor": "ITE",
        "model": "IT8728F V0.5",
        "display_name": "IT8728F",
        "category": "Super I/O / HWM",
        "family": "IT8728",
        "series": "IT87xx",
        "chip_role": "Super I/O Controller",
        "variants": ["IT8728F"],
        "package": "LQFP-128",
        "package_type": "LQFP",
        "document_type": "Datasheet",
        "description": "ITE IT8728F Super I/O 芯片封装图，包含 128 引脚定义、GPIO 复用表和 Super I/O / Hardware Monitor 信号说明。",
        "features": [
            "支持查看 128 引脚封装和 Pin Description 章节",
            "支持显示 GPIO 复用条件、输出驱动能力和寄存器控制属性",
            "支持按模块、信号、引脚快速筛选并定位到封装图",
        ],
        "pin_table_page": 26,
        "pin_description_pages": range(28, 45),
        "gpio_alt_pages": range(46, 51),
        "gpio_reg_pages": range(51, 52),
        "pin_count": 128,
    },
    "it8772_f": {
        "chip_id": "it8772_f",
        "vendor": "ITE",
        "model": "IT8772E V0.4",
        "display_name": "IT8772E / IT8772F",
        "category": "Super I/O / HWM",
        "family": "IT8772",
        "series": "IT87xx",
        "chip_role": "Super I/O Controller",
        "variants": ["IT8772E", "IT8772F"],
        "package": "LQFP-64",
        "package_type": "LQFP",
        "document_type": "Datasheet",
        "description": "ITE IT8772 Super I/O 芯片封装图，包含 64 引脚定义、GPIO 复用条件以及风扇、LPC、UART、硬件监控相关信号。",
        "features": [
            "支持查看 64 引脚封装和 Pin Description 章节",
            "支持显示 GPIO 复用条件、组别、位号和寄存器控制属性",
            "支持按模块、信号、引脚快速筛选并定位到封装图",
        ],
        "pin_table_page": 22,
        "pin_description_pages": range(23, 32),
        "gpio_alt_pages": range(33, 35),
        "gpio_reg_pages": range(35, 36),
        "pin_count": 64,
    },
    "it8786_h": {
        "chip_id": "it8786_h",
        "vendor": "ITE",
        "model": "IT8786E-I V0.7.2",
        "display_name": "IT8786E-I / IT8786H",
        "category": "Super I/O / HWM",
        "family": "IT8786",
        "series": "IT87xx",
        "chip_role": "Super I/O Controller",
        "variants": ["IT8786E-I", "IT8786H"],
        "package": "LQFP-128",
        "package_type": "LQFP",
        "document_type": "Datasheet",
        "description": "ITE IT8786 工业级 Super I/O 芯片封装图，包含 128 引脚定义、eSPI/LPC、GPIO 复用条件和硬件监控相关说明。",
        "features": [
            "支持查看 128 引脚封装和 Pin Description 章节",
            "支持显示 GPIO 复用条件、组别、位号和寄存器控制属性",
            "支持按模块、信号、引脚快速筛选并定位到封装图",
        ],
        "pin_table_page": 24,
        "pin_description_pages": range(25, 42),
        "gpio_alt_pages": range(42, 47),
        "gpio_reg_pages": range(47, 49),
        "pin_count": 128,
    },
}

ITE_SUPERIO_PDFS = {
    "it8625_l": IT8625_PDF,
    "it8728_f": IT8728_PDF,
    "it8772_f": IT8772_PDF,
    "it8786_h": IT8786_PDF,
}

ATTRIBUTE_DESCRIPTIONS = {
    "I": "输入 PAD。",
    "AI": "模拟输入 PAD。",
    "IK": "带施密特触发的输入 PAD。",
    "IKD": "带下拉电阻的施密特触发输入 PAD。",
    "PI": "PCI 规范输入 PAD。",
    "PIO": "PCI 规范双向 PAD。",
    "EIO": "eSPI 规范双向 PAD。",
    "AO": "模拟输出 PAD。",
    "O2": "2mA 输出 PAD。",
    "O4": "4mA 输出 PAD。",
    "O6": "6mA 输出 PAD。",
    "O8": "8mA 输出 PAD。",
    "O16": "16mA 输出 PAD。",
    "AIO2": "带模拟输入的 2mA 双向 PAD。",
    "IOK2": "带施密特触发输入的 2mA 双向 PAD。",
    "IOK4": "带施密特触发输入的 4mA 双向 PAD。",
    "IOK6": "带施密特触发输入的 6mA 双向 PAD。",
    "IOK8": "带施密特触发输入的 8mA 双向 PAD。",
    "PECI": "专用 PECI 双向 PAD。",
    "PWR": "电源引脚。",
    "GND": "地引脚。",
    "DO8": "8mA 数字输出。",
    "DOD8": "8mA 开漏数字输出。",
    "DO16": "16mA 数字输出。",
    "DO24": "24mA 数字输出。",
    "DO24L": "24mA 下拉 / 8mA 上拉数字输出。",
    "DIO8": "8mA 数字输入输出。",
    "DIOD8": "8mA 开漏数字输入输出。",
    "DIOD8-L": "1.8V 接口用 8mA 开漏数字输入输出。",
    "DIO16": "16mA 数字输入输出。",
    "DIOD16": "16mA 开漏数字输入输出。",
    "DIO24": "24mA 数字输入输出。",
    "DIOD24": "24mA 开漏数字输入输出。",
    "DI": "数字输入。",
    "DI-L": "1.8V 接口数字输入。",
    "SST": "SST 专用接口。",
}

SPEC_TEXT_TRANSLATIONS = {
    "Pin Description of Supplies Signals": "电源引脚说明",
    "Pin Description of LPC Bus Interface Signals": "LPC 总线接口引脚说明",
    "Pin Description of Serial Port 1 Signals": "串口 1 引脚说明",
    "Pin Description of Hardware Monitor Signals": "硬件监控引脚说明",
    "Pin Description of Fan Controller Signals": "风扇控制引脚说明",
    "Pin Description of Keyboard Controller Signals": "键盘控制器引脚说明",
    "APC Signals": "APC 电源控制信号",
    "DSW (Deep Sleep Well) Signals": "DSW 深睡电源域信号",
    "Pin Description of Infrared Port Signals": "红外端口引脚说明",
    "Pin Description of PECI/SST Controller Signals": "PECI / SST 控制器引脚说明",
    "Pin Description of PCH & SMBUS_Slave I/F": "PCH 与 SMBus 从设备接口引脚说明",
    "Pin Description of Miscellaneous Signals": "杂项引脚说明",
    "LPC Clock": "LPC 时钟",
    "LPC Address Data": "LPC 地址/数据",
    "LPC LFRAME# Signal": "LPC LFRAME# 信号",
    "SERIRQ Signal": "SERIRQ 信号",
    "eSPI Clock": "eSPI 时钟",
    "eSPI Bi-directional Data": "eSPI 双向数据",
    "eSPI Chip Select": "eSPI 片选",
    "Alert": "告警信号",
    "eSPI Reset": "eSPI 复位",
    "Serial Flash Chip Enable": "串行 Flash 片选",
    "Serial Flash In": "串行 Flash 输入",
    "Serial Flash Out": "串行 Flash 输出",
    "Serial Flash In/Out 2": "串行 Flash IO2",
    "SSPI Clock": "SSPI 时钟",
    "SSPI Chip Enable": "SSPI 片选",
    "SSPI Master In/Slave Out": "SSPI 主入/从出",
    "SSPI Master Out/Slave In": "SSPI 主出/从入",
    "SSPI Busy In": "SSPI Busy 输入",
    "Keyboard Scan Output": "键盘扫描输出",
    "Keyboard Scan Input": "键盘扫描输入",
    "PS/2 Data": "PS/2 数据",
    "Pulse Width Modulation Output": "PWM 输出",
    "These are general-purpose PWM signals.": "这些是通用 PWM 信号。",
    "Tachometer Input": "转速计输入",
    "TMR Output": "定时器输出",
    "Data Terminal Ready": "数据终端就绪",
    "Clear to Send": "允许发送",
    "Ring Indicator": "振铃指示",
    "Data Carrier Detect": "载波检测",
    "UART TX Output": "UART TX 输出",
    "UART RX Input": "UART RX 输入",
    "PECI": "PECI",
    "PECI Request": "PECI 请求",
    "Buffer A Output": "缓冲 A 输出",
    "Buffer B Output": "缓冲 B 输出",
    "Printer Select": "打印机选择",
    "Printer Paper End": "打印机缺纸",
    "Printer Busy": "打印机忙",
    "Printer Acknowledge": "打印机应答",
    "Printer Select Input": "打印机选择输入",
    "Printer Initialize": "打印机初始化",
    "Printer Error": "打印机错误",
    "Printer Auto Line Feed": "打印机自动换行",
    "Printer Strobe": "打印机选通",
    "The value of 0011b is the entry of DBGR/EPP.": "0011b 对应进入 DBGR/EPP。",
    "These pins are the entry of the test mode.": "这些引脚用于进入测试模式。",
    "ADC Input/Alternate GPIO": "ADC 输入/可复用 GPIO",
    "DAC Output": "DAC 输出",
    "CEC": "CEC",
    "Core Power Bypass": "内核电源旁路",
    "Analog Ground for Analog Component": "模拟模块地",
    "LPC Clock 19.2MHz to 33MHz clock for LPC domain functions.": "LPC 时钟。为 LPC 域功能提供 19.2MHz 到 33MHz 时钟。",
    "LPC Address Data": "LPC 地址/数据",
    "LPC LFRAME# Signal": "LPC LFRAME# 信号",
    "SERIRQ Signal This pin is supplied by VFSPI or VCC. VFSPI must be supplied as well if VCC is supplied.": "SERIRQ 信号。该引脚可由 VFSPI 或 VCC 供电；如果 VCC 上电，则 VFSPI 也必须同时供电。",
    "eSPI Clock 20MHz to 66MHz for eSPI domain functions.": "eSPI 时钟。为 eSPI 域功能提供 20MHz 到 66MHz 时钟。",
    "eSPI Bi-directional Data": "eSPI 双向数据。",
    "eSPI Chip Select": "eSPI 片选。",
    "Alert": "告警信号。",
    "eSPI Reset Note this pin takes effect after setting ‘Input Voltage Selection’ to 1.8V.": "eSPI 复位。注意：只有将“Input Voltage Selection”设置为 1.8V 后，该引脚才会生效。",
    "Serial Flash Chip Enable Connected to CE# of serial flash.": "串行 Flash 片选。连接到串行 Flash 的 CE# 引脚。",
    "Serial Flash In Connected to SI of serial flash.": "串行 Flash 输入。连接到串行 Flash 的 SI 引脚。",
    "Serial Flash Out Connected to SO of serial flash.": "串行 Flash 输出。连接到串行 Flash 的 SO 引脚。",
    "Serial Flash In/Out 2 Connected to IO2 of serial flash.": "串行 Flash IO2。连接到串行 Flash 的 IO2 引脚。",
    "SSPI Clock Clock to external device.": "SSPI 时钟。输出到外部设备的时钟。",
    "SSPI Chip Enable Connected to SSCE# of SPI device.": "SSPI 片选。连接到 SPI 设备的 SSCE#。",
    "SSPI Master In/Slave Out Connected to SO of 4-wire SPI device, or connected to SIO of 3-wire SPI device.": "SSPI 主入/从出。连接到四线 SPI 设备的 SO，或连接到三线 SPI 设备的 SIO。",
    "SSPI Master Out/Slave In Connected to SI of 4-wire SPI device.": "SSPI 主出/从入。连接到四线 SPI 设备的 SI。",
    "SSPI Busy In Connected to BUSY of SPI device.": "SSPI Busy 输入。连接到 SPI 设备的 BUSY。",
    "Keyboard Scan Output Keyboard matrix scan output.": "键盘扫描输出。用于键盘矩阵扫描输出。",
    "Keyboard Scan Input Keyboard matrix scan input for switch based keyboard.": "键盘扫描输入。用于开关矩阵键盘的扫描输入。",
    "PS/2 Data 2 sets of PS/2 interface, alternate function of GPIO. PS2DAT0 / 2 correspond to channel 1 / 3 respectively.": "PS/2 数据。共有两组 PS/2 接口，是 GPIO 的复用功能。PS2DAT0 / 2 分别对应通道 1 / 3。",
    "Pulse Width Modulation Output": "PWM 输出。",
    "These are general-purpose PWM signals. PWM0-7 correspond to channel 0-7 respectively.": "这些是通用 PWM 信号。PWM0 到 PWM7 分别对应通道 0 到 7。",
    "Tachometer Input These are tachometer inputs from external fans. They are used for measuring the external fan speed.": "转速计输入。这些引脚接收外部风扇的转速计信号，用于测量风扇转速。",
    "TMR Output": "定时器输出。",
    "Data Terminal Ready DTR# is used to indicate to the MODEM or data set that the device is ready to exchange data. DTR# is activated by setting the appropriate bit in the MCR register to 1. After a Master Reset operation or during Loop mode, DTR# is set to its inactive state.": "数据终端就绪。DTR# 用于通知 MODEM 或数据设备当前已经准备好进行数据交换。将 MCR 寄存器中的相应位设置为 1 后，DTR# 被激活。主复位后或处于回环模式时，DTR# 处于非激活状态。",
    "Clear to Send When the signal is low, it indicates that the MODEM or data set is ready to accept data. The CTS# signal is a MODEM status input whose condition can be tested by reading the MSR register.": "允许发送。当该信号为低时，表示 MODEM 或数据设备已经准备好接收数据。CTS# 是 MODEM 状态输入，可通过读取 MSR 寄存器进行检测。",
    "Ring Indicator When the signal is low, it indicates that a telephone ring signal has been received by the MODEM. The RI# signal is a MODEM status input whose condition can be tested by reading the MSR register.": "振铃指示。当该信号为低时，表示 MODEM 收到了电话振铃信号。RI# 是 MODEM 状态输入，可通过读取 MSR 寄存器进行检测。",
    "Data Carrier Detect When the signal is low, it indicates that the MODEM or data set has detected a carrier. The DCD# signal is a MODEM status input whose condition can be tested by reading the MSR register.": "载波检测。当该信号为低时，表示 MODEM 或数据设备检测到了载波。DCD# 是 MODEM 状态输入，可通过读取 MSR 寄存器进行检测。",
    "UART TX Output UART TX Output from 8051": "UART TX 输出。来自 8051 的 UART 发送输出。",
    "UART RX Input UART RX Input from 8051": "UART RX 输入。输入到 8051 的 UART 接收信号。",
    "PECI This bi-directional pin provides data communication between the PECI host and devices.": "PECI。该双向引脚用于 PECI 主机与设备之间的数据通信。",
    "PECI Request The PECI request is output to PECI devices. When this pin goes low, it requests the system to make the PECI bus available.": "PECI 请求。该信号输出到 PECI 设备；当该引脚拉低时，请求系统使 PECI 总线可用。",
    "Buffer A Output Hardware bypass path from GPI6 to BAO.": "缓冲 A 输出。提供从 GPI6 到 BAO 的硬件旁路路径。",
    "Buffer B Output Hardware bypass path from GPI7 to BBO.": "缓冲 B 输出。提供从 GPI7 到 BBO 的硬件旁路路径。",
    "Printer Select": "打印机选择。",
    "Printer Paper End": "打印机缺纸。",
    "Printer Busy": "打印机忙。",
    "Printer Acknowledge": "打印机应答。",
    "Printer Select Input": "打印机选择输入。",
    "Printer Initialize": "打印机初始化。",
    "Printer Error": "打印机错误。",
    "Printer Auto Line Feed": "打印机自动换行。",
    "Printer Strobe": "打印机选通。",
    "ADC Input/Alternate GPIO These 8 ADC inputs can be used as GPIO ports depending on the ADC channels required.": "ADC 输入/可复用 GPIO。这 8 路 ADC 输入可根据实际 ADC 通道需求复用为 GPIO。",
    "DAC Output": "DAC 输出。",
    "CEC This bi-directional pin provides data communication between the CEC host and devices.": "CEC。该双向引脚用于 CEC 主机与设备之间的数据通信。",
    "Core Power Bypass Internal core power output. External capacitor is required to be connected between this pin and VSS and physically close to this pin. The capacitor type must be low-ESR and MLCC is required.": "内核电源旁路。该引脚输出内部核心电源。必须在该引脚与 VSS 之间外接电容，并尽量靠近该引脚放置；电容需要使用低 ESR 的 MLCC。",
    "Analog Ground for Analog Component": "模拟模块地。",
    "LPC Bus Interface (3.3V/1.8V CMOS I/F) (Supplied by VCC)": "LPC 总线接口（3.3V/1.8V CMOS，VCC 供电）",
    "eSPI Bus Interface (1.8V CMOS I/F) (Supplied by VCC)": "eSPI 总线接口（1.8V CMOS，VCC 供电）",
    "eSPI Bus Interface (1.8V CMOS I/F)": "eSPI 总线接口（1.8V CMOS）",
    "105 FSCK O4 Serial Flash Clock": "外部串行 Flash 接口（3.3V/1.8V CMOS，VFSPI 供电）",
    "Serial Peripheral Interface (3.3V CMOS I/F)": "串行外设接口（3.3V CMOS）",
    "KB Matrix Interface (3.3V CMOS I/F)": "键盘矩阵接口（3.3V CMOS）",
    "89, 85 PS2CLK2 IOK8 PS/2 CLK": "PS/2 接口（3.3V CMOS）",
    "PWM Interface (3.3V CMOS I/F)": "PWM 接口（3.3V CMOS）",
    "TMR Interface (3.3V CMOS I/F)": "TMR 定时器接口（3.3V CMOS）",
    "35 RTS1# O2 Request to Send": "UART / Modem 控制接口（3.3V CMOS）",
    "UART Interface (3.3V CMOS I/F)": "UART 接口（3.3V CMOS）",
    "Platform Environment Control Interface Interface (3.3V CMOS I/F)": "平台环境控制接口 PECI（3.3V CMOS）",
    "Hardware Bypass Interface (3.3V CMOS I/F)": "硬件旁路接口（3.3V CMOS）",
    "Parallel Port Interface (3.3V CMOS I/F)": "并口接口（3.3V CMOS）",
    "99-93 These hardware straps are used to identify the version for firmware usage.": "硬件 Strap（3.3V CMOS）",
    "ADC Interface (3.3V CMOS I/F)": "ADC 接口（3.3V CMOS）",
    "DAC Interface (3.3V CMOS I/F)": "DAC 接口（3.3V CMOS）",
    "CEC Interface (3.3V CMOS I/F)": "CEC 接口（3.3V CMOS）",
    "106 VFSPI I Standby Power Supply of 3.3V/1.8V": "电源引脚（VFSPI 3.3V/1.8V 待机电源）",
}

LPC_DUAL_VOLTAGE_ALIASES = {"LPCCLK", "LFRAME#"} | {f"LAD{index}" for index in range(4)}
FSPI_DUAL_VOLTAGE_ALIASES = {"SERIRQ", "FSCK", "FSCE#", "FMOSI", "FMISO", "FDIO2", "FDIO3"}
SMBUS_DUAL_VOLTAGE_ALIASES = {f"SMCLK{index}" for index in range(6)} | {f"SMDAT{index}" for index in range(6)}

MODULE_DEFS = [
    {"id": "power", "name": "Power", "patterns": [r"^VSS$", r"^VCC$", r"^VCORE$", r"^VSTBY\d*$", r"^VFSPI$", r"^AVCC\d*$", r"^AVSS$", r"^GNDA$", r"^GNDD$", r"^3VSB$", r"^SYS_3VSB$", r"^VBAT$", r"^VCCBT$"]},
    {
        "id": "battery",
        "name": "Battery / Sense",
        "patterns": [
            r"^VBUS$",
            r"^ACN$",
            r"^ACP$",
            r"^BATDRV$",
            r"^SRN$",
            r"^SRP$",
            r"^VSYS$",
            r"^CELL_BATPRESZ$",
            r"^VCELL$",
            r"^CSP$",
            r"^CSN$",
            r"^TS$",
            r"^INT_N$",
        ],
    },
    {
        "id": "charger",
        "name": "Charger / Power Path",
        "patterns": [
            r"^CHRG_OK$",
            r"^OTG/VAP/FRS$",
            r"^ILIM_HIZ$",
            r"^PROCHOT$",
            r"^CMPIN$",
            r"^CMPOUT$",
            r"^COMP[12]$",
            r"^IADPT$",
            r"^IBAT$",
            r"^PSYS$",
            r"^REGN$",
            r"^HIDRV[12]$",
            r"^LODRV[12]$",
            r"^BTST[12]$",
            r"^SW[12]$",
        ],
    },
    {
        "id": "thermal",
        "name": "Thermal / Sensor",
        "patterns": [
            r"^DP[12]$",
            r"^DN[12]$",
            r"^THERM$",
            r"^THERM2$",
            r"^ALERT$",
            r"^ALERT/THERM2$",
        ],
    },
    {"id": "fan", "name": "Fan / PWM", "patterns": [r"^PWM\d+$", r"^TACH\d+[AB]?$", r"^FANIN\d+$", r"^FANOUT\d+$", r"^FAN_TAC\d+$", r"^FAN_CTL\d+$"]},
    {"id": "keyboard", "name": "Keyboard", "patterns": [r"^KSO\d+$", r"^KSI\d+$"]},
    {
        "id": "espi_lpc",
        "name": "eSPI / LPC",
        "patterns": [
            r"^EIO\d+$",
            r"^ESCK$",
            r"^ECS#$",
            r"^ALERT#$",
            r"^LPCCLK$",
            r"^LAD\d$",
            r"^LFRAME#$",
            r"^SERIRQ$",
            r"^LPCRST#$",
            r"^ERST#$",
            r"^CLKRUN#$",
            r"^ECSMI#$",
            r"^ECSCI#$",
            r"^GA20$",
            r"^KBRST#$",
            r"^WRST#$",
            r"^PWUREQ#$",
            r"^L80HLAT$",
            r"^L80LLAT$",
            r"^PLTRST#$",
            r"^LPCPD#$",
            r"^ESPI_[A-Z0-9_\[\]]+$",
            r"^LPC_RST_L$",
            r"^KBRST_L$",
        ],
    },
    {"id": "fspi", "name": "FSPI", "patterns": [r"^FSCK$", r"^FSCE#$", r"^FMOSI$", r"^FMISO$", r"^FDIO\d+$", r"^SPI\d?_[A-Z0-9_\[\]]+$", r"^SPI_ROM_[A-Z0-9_]+$", r"^SPI_TPM_CS_L$"]},
    {"id": "sspi", "name": "SSPI", "patterns": [r"^SSCK$", r"^SSCE\d#$", r"^SMISO$", r"^SMOSI$", r"^SBUSY$"]},
    {"id": "smbus", "name": "SMBus / I2C / I3C", "patterns": [r"^SMCLK\d+(?:ALT)?$", r"^SMDAT\d+$", r"^I2C\d_[A-Z0-9_]+$", r"^I3C\d_[A-Z0-9_]+$", r"^SMBUS\d_[A-Z0-9_]+$"]},
    {"id": "serial", "name": "Serial / UART", "patterns": [r"^SIN\d+$", r"^SOUT\d+$", r"^TXD$", r"^RXD$", r"^CTS\d?#$", r"^DSR\d?#$", r"^DCD\d?#$", r"^DTR\d?#$", r"^RTS\d?#$", r"^RIG\d?#$", r"^RI\d?#$", r"^UART\d_[A-Z0-9_]+$"]},
    {"id": "cir", "name": "CIR", "patterns": [r"^CTX\d+$", r"^CRX\d+$"]},
    {"id": "egpc", "name": "EGPC", "patterns": [r"^EGAD$", r"^EGCS#$", r"^EGCLK$"]},
    {"id": "peci", "name": "PECI", "patterns": [r"^PECI$", r"^PECIRQT#$"]},
    {"id": "pcie", "name": "PCIe / Clock Req", "patterns": [r"^PCIE_RST\d?_L$", r"^CLK_REQ\d+_L$"]},
    {"id": "usb", "name": "USB / OC", "patterns": [r"^USB_OC\d_L$"]},
    {"id": "audio", "name": "Audio / Speaker", "patterns": [r"^SPKR$", r"^SD0_[A-Z0-9\[\]]+$"]},
    {"id": "security", "name": "Security / PSP", "patterns": [r"^PSP_INTR\d+$", r"^SHUTDOWN_L$"]},
    {"id": "parallel", "name": "Parallel Port", "patterns": [r"^ACK#$", r"^BUSY$", r"^ERR#$", r"^PE$", r"^SLCT$", r"^SLIN#$", r"^INIT#$", r"^AFD#$", r"^STB#$", r"^PD\d$"]},
    {"id": "analog", "name": "ADC / DAC", "patterns": [r"^ADC\d+$", r"^DAC\d+$", r"^VIN\d+(?:\(.+\))?$", r"^TMPIN\d+$", r"^VREF$", r"^VLDT_?12$", r"^5VSB_SEN$", r"^5VDUAL$"]},
    {"id": "timer", "name": "Timer", "patterns": [r"^TMA\d+$", r"^TMB\d+$", r"^XLP_OUT$", r"^IO80_OUT\d*$"]},
    {"id": "wake", "name": "Wake / Power Control", "patterns": [r"^PWRSW$", r"^AC_IN#$", r"^LID_SW#$", r"^BTN#$", r"^PWR_BTN_L$", r"^WAKE_L$", r"^AC_PRES$", r"^GENINT\d_L$", r"^PWRON#$", r"^PSON#$", r"^PANSWH#$", r"^SUSB#$", r"^SUSC#$", r"^SUSACK#$", r"^SUSWARN#$", r"^SLP_SUS#$", r"^RSMRST#$", r"^ATXPG$", r"^DPWROK$", r"^PWRGD\d+$", r"^CPU_PG$", r"^VCORE_EN$", r"^VLDT_EN$", r"^3VSBSW#$", r"^5VSB_CTRL#$"]},
    {"id": "cec", "name": "CEC", "patterns": [r"^CEC$"]},
    {"id": "strap", "name": "ID / Strap", "patterns": [r"^ID\d+$", r"^RST_STRAP$", r"^PKG_STRAP\d+$", r"^JP\d+$", r"^VIH_VIL_SEL$", r"^DSW_EUP_SEL$", r"^K8PWR_EN$", r"^LPC_ESPI_SEL$"]},
    {"id": "gpio", "name": "GPIO", "patterns": [r"^GP[A-Z]\d+$", r"^[AE]?GPIO\d+$", r"^S0A3_GPIO$", r"^BLINK$", r"^LLB_L$", r"^TMU_CLK_OUT\d+$", r"^DF_VRCONTEXT_\d+$", r"^GFX10_CAC_IPIO\d+$", r"^OSCIN$"]},
]


def _compile_module_patterns():
    compiled = []
    for module in MODULE_DEFS:
        compiled.append(
            {
                "id": module["id"],
                "name": module["name"],
                "patterns": [re.compile(pattern, re.IGNORECASE) for pattern in module["patterns"]],
            }
        )
    return compiled


COMPILED_MODULES = _compile_module_patterns()


def split_aliases(label: str) -> list[str]:
    return [part.strip() for part in label.split("/") if part.strip()]


def classify_aliases(aliases: list[str]) -> list[str]:
    matches: list[str] = []
    for module in COMPILED_MODULES:
        if any(pattern.fullmatch(alias) for alias in aliases for pattern in module["patterns"]):
            matches.append(module["id"])
    if not matches:
        matches.append("other")
    return matches


def primary_module(aliases: list[str]) -> str:
    for alias in aliases:
        for module in COMPILED_MODULES:
            if any(pattern.fullmatch(alias) for pattern in module["patterns"]):
                return module["id"]
    return "other"


def module_name(module_id: str) -> str:
    for module in MODULE_DEFS:
        if module["id"] == module_id:
            return module["name"]
    return "Other"


def top_module_names(modules: list[dict], limit: int = 4) -> list[str]:
    ordered = sorted(modules, key=lambda item: (-item["count"], item["name"].casefold()))
    return [item["name"] for item in ordered[:limit]]


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _normalize_gpio_text(text: str) -> str:
    text = _normalize_text(text.replace("/ ", "/"))
    replacements = {
        "LPCCLK/E SCK": "LPCCLK/ESCK",
        "LFRAME#/ ECS#": "LFRAME#/ECS#",
        "SERIRQ/A LERT#": "SERIRQ/ALERT#",
        "RXD BBO T SIN0": "RXD / BBO / TSIN0",
    }
    return replacements.get(text, text)


def expand_pin_numbers(text: str) -> list[int]:
    numbers: list[int] = []
    for part in _normalize_text(text).split(","):
        token = part.strip()
        if not token:
            continue
        if re.fullmatch(r"\d+-\d+", token):
            start_text, end_text = token.split("-")
            start = int(start_text)
            end = int(end_text)
            step = 1 if end >= start else -1
            numbers.extend(list(range(start, end + step, step)))
            continue
        if token.isdigit():
            numbers.append(int(token))
    return numbers


def expand_signal_aliases(text: str) -> list[str]:
    aliases: list[str] = []
    for chunk in _normalize_text(text).split(","):
        token = chunk.strip()
        if not token:
            continue
        match = re.fullmatch(r"([A-Za-z0-9_]+)\[([0-9,:]+)\](#?)", token)
        if not match:
            aliases.append(token)
            continue
        prefix, index_text, suffix = match.groups()
        if ":" in index_text:
            start_text, end_text = index_text.split(":")
            start = int(start_text)
            end = int(end_text)
            step = 1 if end >= start else -1
            aliases.extend(f"{prefix}{value}{suffix}" for value in range(start, end + step, step))
            continue
        aliases.extend(f"{prefix}{value}{suffix}" for value in index_text.split(","))
    return aliases


def describe_attribute(attribute: str) -> str:
    parts = [part.strip() for part in attribute.split("/") if part.strip()]
    descriptions = [ATTRIBUTE_DESCRIPTIONS[part] for part in parts if part in ATTRIBUTE_DESCRIPTIONS]
    if descriptions:
        return " / ".join(descriptions)
    return ""


def translate_spec_text(text: str) -> str:
    normalized = _normalize_text(text)
    if not normalized:
        return ""
    if normalized in SPEC_TEXT_TRANSLATIONS:
        return SPEC_TEXT_TRANSLATIONS[normalized]

    translated = normalized
    replacements = [
        ("This bi-directional pin provides data communication between the ", "该双向引脚用于 "),
        (" host and devices.", " 主机与设备之间的数据通信。"),
        ("Connected to ", "连接到 "),
        (" of serial flash.", " 的串行 Flash 引脚。"),
        (" of SPI device.", " 的 SPI 设备引脚。"),
        ("This pin is supplied by ", "该引脚由 "),
        (" must be supplied as well if ", " 也必须同时供电，如果 "),
        (" is supplied.", " 已供电。"),
        ("When the signal is low, it indicates that ", "当该信号为低时，表示 "),
        (" signal is a MODEM status input whose condition can be tested by reading the MSR register.", " 信号是 MODEM 状态输入，可通过读取 MSR 寄存器进行检测。"),
        ("These are ", "这些是 "),
        (" respectively.", "，分别对应。"),
        ("Clock to external device.", "输出到外部设备的时钟。"),
        ("Internal core power output.", "内部核心电源输出。"),
        ("External capacitor is required to be connected between this pin and VSS and physically close to this pin.", "必须在该引脚与 VSS 之间外接电容，并尽量靠近该引脚放置。"),
        ("The capacitor type must be low-ESR and MLCC is required.", "电容必须使用低 ESR 的 MLCC。"),
    ]
    for source, target in replacements:
        translated = translated.replace(source, target)
    return translated


def translate_table_label(text: str) -> str:
    normalized = _normalize_text(text)
    match = re.match(r"Table\s+([0-9\-]+)\.", normalized, re.IGNORECASE)
    if match:
        return f"表 {match.group(1)}"
    return normalized


def _pin_record(pin_number: int, side: str, side_index: int, label: str) -> dict:
    aliases = split_aliases(label)
    modules = classify_aliases(aliases)
    return {
        "pin_number": pin_number,
        "side": side,
        "side_index": side_index,
        "label": label,
        "display_name": aliases[0] if aliases else label,
        "aliases": aliases,
        "modules": modules,
        "primary_module": primary_module(aliases),
    }


def _base_pin_record(pin_number: int, label: str, pin_ref: str = "") -> dict:
    aliases = split_aliases(label)
    display_name = aliases[0] if aliases else label
    return {
        "pin_number": pin_number,
        "pin_ref": pin_ref or f"P{pin_number}",
        "pin_index_label": str(pin_number),
        "label": label,
        "display_name": display_name,
        "aliases": aliases,
        "modules": classify_aliases(aliases),
        "primary_module": primary_module(aliases),
    }


def _is_signal_label(text: str) -> bool:
    normalized = re.sub(r"\s*/\s*", "/", _normalize_text(text))
    if not normalized:
        return False
    if normalized != normalized.upper():
        return False
    return bool(re.fullmatch(r"[A-Z0-9_/#()+\-~, ]+", normalized)) and any(char.isalpha() for char in normalized)


def _assign_standard_package_sides(pins: list[dict], side_counts: tuple[int, int, int, int]) -> None:
    left_count, bottom_count, right_count, top_count = side_counts
    total = left_count + bottom_count + right_count + top_count
    if total != len(pins):
        raise ValueError(f"side_counts total {total} does not match pin count {len(pins)}")

    index = 0
    for side_index in range(left_count):
        pins[index]["side"] = "left"
        pins[index]["side_index"] = side_index
        index += 1
    for side_index in range(bottom_count):
        pins[index]["side"] = "bottom"
        pins[index]["side_index"] = side_index
        index += 1
    for offset in range(right_count):
        pins[index]["side"] = "right"
        pins[index]["side_index"] = right_count - 1 - offset
        index += 1
    for offset in range(top_count):
        pins[index]["side"] = "top"
        pins[index]["side_index"] = top_count - 1 - offset
        index += 1


def _manual_sections(entries: list[tuple[str, int]]) -> list[dict]:
    return [{"title": title, "page": page} for title, page in entries]


def _sections_or_manual(pdf_path: Path, entries: list[tuple[str, int]]) -> list[dict]:
    sections = extract_top_sections(pdf_path)
    return sections or _manual_sections(entries)


def _operating_voltage_profile(
    summary: str,
    *,
    supports_1_8v=None,
    supports_3_3v=None,
    supports_1_8v_input_only: bool = False,
    supports_5v_tolerant: bool = False,
    notes: list[str] | None = None,
) -> dict:
    return {
        "supports_1_8v": supports_1_8v,
        "supports_3_3v": supports_3_3v,
        "supports_1_8v_input_only": supports_1_8v_input_only,
        "supports_5v_tolerant": supports_5v_tolerant,
        "summary": summary,
        "notes": list(dict.fromkeys(notes or [])),
    }


def _range_voltage_profile(
    range_text: str,
    *,
    min_value: float | None,
    max_value: float | None,
    notes: list[str] | None = None,
) -> dict:
    supports_1_8v = None if min_value is None or max_value is None else min_value <= 1.8 <= max_value
    supports_3_3v = None if min_value is None or max_value is None else min_value <= 3.3 <= max_value
    return _operating_voltage_profile(
        f"引脚工作范围 {range_text}",
        supports_1_8v=supports_1_8v,
        supports_3_3v=supports_3_3v,
        notes=notes,
    )


def _first_sentence(text: str) -> str:
    normalized = _normalize_text(text)
    if not normalized:
        return ""
    match = re.search(r"(.+?[。.!?])(?:\s|$)", normalized)
    return match.group(1) if match else normalized


def _simple_detail_entry(
    *,
    page: int,
    table: str,
    table_cn: str,
    interface: str,
    interface_cn: str,
    signal_text: str,
    summary: str,
    summary_cn: str,
    description: str,
    description_cn: str,
    attribute: str = "",
    attribute_description: str = "",
) -> dict:
    return {
        "page": page,
        "table": table,
        "table_cn": table_cn,
        "interface": interface,
        "interface_cn": interface_cn,
        "signal_text": signal_text,
        "signals": split_aliases(signal_text),
        "attribute": attribute,
        "attribute_description": attribute_description,
        "summary": summary,
        "summary_cn": summary_cn,
        "description": description,
        "description_cn": description_cn,
    }


def _select_words(words: list[tuple], predicate) -> list[tuple]:
    return [word for word in words if predicate(word)]


def _group_words_by_line(page: fitz.Page, tolerance: float = 1.8) -> list[dict]:
    words = sorted(page.get_text("words"), key=lambda word: (((word[1] + word[3]) * 0.5), word[0]))
    lines: list[dict] = []
    for word in words:
        y = (word[1] + word[3]) * 0.5
        if lines and abs(lines[-1]["y"] - y) <= tolerance:
            lines[-1]["words"].append(word)
            lines[-1]["ys"].append(y)
            lines[-1]["y"] = sum(lines[-1]["ys"]) / len(lines[-1]["ys"])
        else:
            lines.append({"y": y, "ys": [y], "words": [word]})
    for line in lines:
        line["words"] = sorted(line["words"], key=lambda word: word[0])
        line["text"] = _normalize_text(" ".join(word[4] for word in line["words"]))
    return lines


def parse_it5570_top_view(pdf_path: Path) -> list[dict]:
    doc = fitz.open(pdf_path)
    try:
        page = doc.load_page(IT5570_TOP_VIEW_PAGE)
        words = page.get_text("words")
    finally:
        doc.close()

    left_labels = sorted(
        _select_words(words, lambda word: (not word[4].isdigit()) and word[2] < 200.0 and 260.0 <= ((word[1] + word[3]) * 0.5) <= 470.0),
        key=lambda word: ((word[1] + word[3]) * 0.5),
    )
    bottom_labels = sorted(
        _select_words(words, lambda word: (not word[4].isdigit()) and 210.0 <= ((word[0] + word[2]) * 0.5) <= 430.0 and 490.0 <= word[1] <= 560.0),
        key=lambda word: ((word[0] + word[2]) * 0.5),
    )
    right_labels = sorted(
        _select_words(words, lambda word: (not word[4].isdigit()) and word[0] > 450.0 and 260.0 <= ((word[1] + word[3]) * 0.5) <= 470.0),
        key=lambda word: ((word[1] + word[3]) * 0.5),
    )
    top_labels = sorted(
        _select_words(words, lambda word: (not word[4].isdigit()) and 210.0 <= ((word[0] + word[2]) * 0.5) <= 430.0 and 145.0 <= word[1] <= 240.0),
        key=lambda word: ((word[0] + word[2]) * 0.5),
    )

    if not (len(left_labels) == len(bottom_labels) == len(right_labels) == len(top_labels) == 32):
        raise RuntimeError(
            "Failed to parse IT5570 top-view pin labels: "
            f"left={len(left_labels)} bottom={len(bottom_labels)} right={len(right_labels)} top={len(top_labels)}"
        )

    pins: list[dict] = []
    for index, word in enumerate(left_labels):
        pins.append(_pin_record(index + 1, "left", index, word[4]))
    for index, word in enumerate(bottom_labels):
        pins.append(_pin_record(index + 33, "bottom", index, word[4]))
    for index, word in enumerate(right_labels):
        pins.append(_pin_record(96 - index, "right", index, word[4]))
    for index, word in enumerate(top_labels):
        pins.append(_pin_record(128 - index, "top", index, word[4]))

    return sorted(pins, key=lambda pin: pin["pin_number"])


def _line_is_pin_description_row_start(line: dict) -> bool:
    if not (150.0 <= line["y"] <= 520.0):
        return False
    has_pin = any(60.0 <= word[0] < 120.0 and re.fullmatch(r"[0-9,\-]+", word[4]) for word in line["words"])
    has_signal = any(126.0 <= word[0] < 205.0 and any(char.isalpha() for char in word[4]) for word in line["words"])
    has_attribute = any(205.0 <= word[0] < 245.0 for word in line["words"])
    return has_pin and has_signal and has_attribute


def _finalize_pin_description_row(current_row: dict | None, rows: list[dict]) -> None:
    if not current_row:
        return
    pin_text = _normalize_text(" ".join(current_row["pin_words"]))
    signal_text = _normalize_text(" ".join(current_row["signal_words"]))
    attribute = _normalize_text(" ".join(current_row["attribute_words"]))
    description_lines = [_normalize_text(line) for line in current_row["description_lines"] if _normalize_text(line)]
    summary = description_lines[0] if description_lines else ""
    rows.append(
        {
            "page": current_row["page"],
            "table": current_row["table"],
            "table_cn": translate_table_label(current_row["table"]),
            "interface": current_row["interface"],
            "interface_cn": translate_spec_text(current_row["interface"]),
            "pin_text": pin_text,
            "pin_numbers": expand_pin_numbers(pin_text),
            "signal_text": signal_text,
            "signals": expand_signal_aliases(signal_text),
            "attribute": attribute,
            "attribute_description": describe_attribute(attribute),
            "summary": summary,
            "summary_cn": translate_spec_text(summary),
            "description": _normalize_text(" ".join(description_lines)),
            "description_cn": translate_spec_text(_normalize_text(" ".join(description_lines))),
        }
    )


def parse_pin_descriptions(pdf_path: Path) -> list[dict]:
    doc = fitz.open(pdf_path)
    try:
        rows: list[dict] = []
        current_table = ""
        current_interface = ""
        current_row: dict | None = None

        for page_no in PIN_DESCRIPTION_PAGES:
            page = doc.load_page(page_no - 1)
            for line in _group_words_by_line(page):
                text = line["text"]
                if not text or "www.ite.com.tw" in text or "IT5570" in text:
                    continue
                if re.match(r"Table 5-\d+\.", text):
                    _finalize_pin_description_row(current_row, rows)
                    current_row = None
                    current_table = text
                    current_interface = ""
                    continue
                if text.startswith("Pin(s) No.") or text.startswith("Signal Pin(s)") or text == "Pin(s) No. Signal Attribute Description":
                    continue
                if current_table and not current_row and not _line_is_pin_description_row_start(line):
                    if any(word[0] < 120.0 for word in line["words"]) and any(word[0] > 150.0 for word in line["words"]):
                        current_interface = text
                    continue
                if _line_is_pin_description_row_start(line):
                    _finalize_pin_description_row(current_row, rows)
                    current_row = {
                        "page": page_no,
                        "table": current_table,
                        "interface": current_interface,
                        "pin_words": [word[4] for word in line["words"] if 60.0 <= word[0] < 120.0],
                        "signal_words": [word[4] for word in line["words"] if 126.0 <= word[0] < 205.0],
                        "attribute_words": [word[4] for word in line["words"] if 205.0 <= word[0] < 245.0],
                        "description_lines": [_normalize_text(" ".join(word[4] for word in line["words"] if word[0] >= 253.0))],
                    }
                    continue
                if current_row:
                    current_row["pin_words"].extend(word[4] for word in line["words"] if 60.0 <= word[0] < 120.0)
                    current_row["signal_words"].extend(word[4] for word in line["words"] if 126.0 <= word[0] < 205.0)
                    current_row["attribute_words"].extend(word[4] for word in line["words"] if 205.0 <= word[0] < 245.0)
                    description_line = _normalize_text(" ".join(word[4] for word in line["words"] if word[0] >= 253.0))
                    if description_line:
                        current_row["description_lines"].append(description_line)

        _finalize_pin_description_row(current_row, rows)
        return [row for row in rows if row["pin_numbers"]]
    finally:
        doc.close()


def _line_is_gpio_row_start(line: dict) -> bool:
    if line["y"] < 140.0 or line["y"] > 545.0:
        return False
    has_index = any(92.0 <= word[0] < 106.0 and re.fullmatch(r"-|\d+", word[4]) for word in line["words"])
    has_addr = any(106.0 <= word[0] < 142.0 and re.fullmatch(r"[0-9A-Fa-f]{4}h|-", word[4]) for word in line["words"])
    has_pin = any(142.0 <= word[0] < 160.0 and re.fullmatch(r"-|\d+", word[4]) for word in line["words"])
    return has_index and has_addr and has_pin


def _explicit_gpio_group(line: dict) -> str:
    for word in line["words"]:
        if word[0] < 90.0 and re.fullmatch(r"GPIO[A-Z]+", word[4]):
            return word[4]
    return ""


def parse_gpio_alt_functions(pdf_path: Path) -> dict[int, dict]:
    doc = fitz.open(pdf_path)
    try:
        rows: dict[int, dict] = {}
        for page_no in GPIO_ALT_PAGES:
            page = doc.load_page(page_no - 1)
            lines = _group_words_by_line(page)
            start_indexes = [index for index, line in enumerate(lines) if _line_is_gpio_row_start(line)]
            current_group = ""
            for start_pos, start_index in enumerate(start_indexes):
                group = _explicit_gpio_group(lines[start_index])
                if group:
                    current_group = group
                end_index = start_indexes[start_pos + 1] - 1 if start_pos + 1 < len(start_indexes) else len(lines) - 1
                while end_index > start_index and ("www.ite.com.tw" in lines[end_index]["text"] or "IT5570" in lines[end_index]["text"] or lines[end_index]["text"].startswith("Note:")):
                    end_index -= 1

                column_map: dict[str, list[str]] = defaultdict(list)
                for line in lines[start_index : end_index + 1]:
                    for word in line["words"]:
                        x = word[0]
                        token = word[4]
                        if x < 90.0:
                            if re.fullmatch(r"GPIO[A-Z]+", token):
                                column_map["group"].append(token)
                        elif x < 106.0:
                            column_map["index"].append(token)
                        elif x < 142.0:
                            column_map["addr"].append(token)
                        elif x < 160.0:
                            column_map["pin"].append(token)
                        elif x < 210.0:
                            column_map["func1"].append(token)
                        elif x < 283.0:
                            column_map["cond1"].append(token)
                        elif x < 325.0:
                            column_map["func2"].append(token)
                        elif x < 383.0:
                            column_map["cond2"].append(token)
                        elif x < 421.0:
                            column_map["func3"].append(token)
                        elif x < 492.0:
                            column_map["cond3"].append(token)
                        elif x < 540.0:
                            column_map["output"].append(token)
                        elif x < 561.0:
                            column_map["schmitt"].append(token)
                        elif x < 594.0:
                            column_map["pull_cap"].append(token)
                        elif x < 619.0:
                            column_map["default_pull"].append(token)
                        elif x < 640.0:
                            column_map["vt5"].append(token)
                        elif x < 664.0:
                            column_map["v18"].append(token)
                        else:
                            column_map["mode"].append(token)

                row = {key: _normalize_gpio_text(" ".join(values)) for key, values in column_map.items()}
                row["group"] = row.get("group") or current_group
                row["page"] = page_no
                if not re.fullmatch(r"[0-9A-Fa-f]{4}h", row.get("addr", "")):
                    continue
                if not re.fullmatch(r"\d+", row.get("pin", "")):
                    continue
                row["pin_number"] = int(row["pin"])
                rows[row["pin_number"]] = row
        return rows
    finally:
        doc.close()


def _build_pin_detail_map(details: list[dict]) -> dict[int, list[dict]]:
    detail_map: dict[int, list[dict]] = defaultdict(list)
    for detail in details:
        for pin_number in detail["pin_numbers"]:
            detail_map[pin_number].append(detail)
    return detail_map


def _voltage_profile(pin: dict, detail_entries: list[dict], gpio_alt_info: dict | None) -> dict:
    aliases = set(pin.get("aliases", []))
    supports_1_8v = False
    supports_3_3v = False
    supports_1_8v_input_only = False
    supports_5v_tolerant = False
    notes: list[str] = []

    for detail in detail_entries:
        interface_text = " ".join([detail.get("table", ""), detail.get("interface", ""), detail.get("summary", ""), detail.get("description", "")])
        if "3.3V/1.8V" in interface_text:
            supports_1_8v = True
            supports_3_3v = True
        elif "1.8V CMOS" in interface_text:
            supports_1_8v = True
        elif "3.3V CMOS" in interface_text:
            supports_3_3v = True

    if aliases & LPC_DUAL_VOLTAGE_ALIASES:
        supports_1_8v = True
        supports_3_3v = True
        notes.append("LPC 引脚可随 VCC 切换到 1.8V 或 3.3V 工作。")
    if aliases & FSPI_DUAL_VOLTAGE_ALIASES:
        supports_1_8v = True
        supports_3_3v = True
        notes.append("FSPI 引脚跟随 VFSPI 电源轨，可工作在 1.8V 或 3.3V。")
    if aliases & SMBUS_DUAL_VOLTAGE_ALIASES:
        supports_1_8v = True
        supports_3_3v = True
        notes.append("SMBus 引脚支持 1.8V 或 3.3V 开漏方式，内部上拉必须关闭。")

    if gpio_alt_info is not None:
        supports_3_3v = True
        if gpio_alt_info.get("v18") == "Y":
            supports_1_8v = True
            supports_1_8v_input_only = True
            notes.append("GPIO 复用表标注该引脚在关闭复用功能后支持 1.8V 输入。")
        if gpio_alt_info.get("vt5") == "Y":
            supports_5v_tolerant = True

    notes = list(dict.fromkeys(notes))

    if supports_1_8v and supports_3_3v and supports_1_8v_input_only:
        summary = "支持 3.3V 输入/输出；在特定功能或 GPIO 输入模式下支持 1.8V。"
    elif supports_1_8v and supports_3_3v:
        summary = "同时支持 1.8V 和 3.3V 工作。"
    elif supports_1_8v:
        summary = "支持 1.8V 工作。"
    elif supports_3_3v:
        summary = "支持 3.3V 工作。"
    else:
        summary = "PDF 中未解析到明确的 1.8V / 3.3V 切换说明。"

    return {
        "supports_1_8v": supports_1_8v,
        "supports_3_3v": supports_3_3v,
        "supports_1_8v_input_only": supports_1_8v_input_only,
        "supports_5v_tolerant": supports_5v_tolerant,
        "summary": summary,
        "notes": notes,
    }


def build_signal_index(pins: list[dict]) -> list[dict]:
    signal_map: dict[str, set[int]] = defaultdict(set)
    for pin in pins:
        for alias in pin["aliases"]:
            signal_map[alias].add(pin["pin_number"])
    return [
        {"signal": signal, "pins": sorted(pin_numbers)}
        for signal, pin_numbers in sorted(signal_map.items(), key=lambda item: (item[0].upper(), min(item[1])))
    ]


def build_module_index(pins: list[dict]) -> list[dict]:
    module_map: dict[str, set[int]] = defaultdict(set)
    for pin in pins:
        for module in pin["modules"]:
            module_map[module].add(pin["pin_number"])

    modules = []
    for module_id in [module["id"] for module in MODULE_DEFS] + ["other"]:
        if module_id not in module_map:
            continue
        modules.append(
            {
                "id": module_id,
                "name": module_name(module_id),
                "pins": sorted(module_map[module_id]),
                "count": len(module_map[module_id]),
            }
        )
    return modules


IT8613_KNOWN_ATTRIBUTES = [
    "DIOD8-L",
    "DIOD24",
    "DIOD16",
    "DIOD8",
    "DIO24",
    "DIO16",
    "DIO8",
    "DO24L",
    "DO24",
    "DO16",
    "DOD8",
    "DO8",
    "DI-L",
    "PECI",
    "SST",
    "PWR",
    "GND",
    "DI",
    "AI",
    "AO",
]
IT8613_INPUT_ATTRIBUTES = {"DI", "DI-L", "DIO8", "DIO16", "DIO24", "DIOD8", "DIOD8-L", "DIOD16", "DIOD24", "PECI", "SST"}
IT8613_OUTPUT_ATTRIBUTES = {"DO8", "DO16", "DO24", "DO24L", "DOD8", "AO"}
IT8613_SPECIAL_1V8_INPUT_ALIASES = {"SUSB#", "SUSC#", "LRESET#", "SERIRQ", "GP21", "GP22", "GP23"}
IT8613_LPC_ALIASES = {"LAD0", "LAD1", "LAD2", "LAD3", "LFRAME#", "SERIRQ", "LRESET#", "PCICLK"}
IT8613_GPIO_PROPERTY_LABELS = {
    "GPIO Control in S3/S5": "S3/S5 GPIO 控制",
    "Multi-pin selection (Index 25h)": "多功能选择 (Index 25h)",
    "Multi-pin selection (Index 26h)": "多功能选择 (Index 26h)",
    "Multi-pin selection (Index 27h)": "多功能选择 (Index 27h)",
    "Multi-pin selection (Index 28h)": "多功能选择 (Index 28h)",
    "Multi-pin selection ( Index 29h)": "多功能选择 (Index 29h)",
    "Multi-pin selection-1 (Index 29h)": "多功能选择-1 (Index 29h)",
    "Multi-pin selection-2 (Index 2Dh)": "多功能选择-2 (Index 2Dh)",
    "Pin polarity (Index B0h)": "引脚极性 (Index B0h)",
    "Pin polarity (Index B1h)": "引脚极性 (Index B1h)",
    "Pin polarity (Index B2h)": "引脚极性 (Index B2h)",
    "Pin polarity (Index B3h)": "引脚极性 (Index B3h)",
    "Pin polarity (Index B4h)": "引脚极性 (Index B4h)",
    "Pin polarity*Note4 (Index B5h)": "引脚极性 (Index B5h)",
    "Internal pull-up enable (Index B8h)": "内部上拉 (Index B8h)",
    "Internal pull-up enable (Index B9h)": "内部上拉 (Index B9h)",
    "Internal pull-up enable (Index BAh)": "内部上拉 (Index BAh)",
    "Internal pull-up enable (Index BBh)": "内部上拉 (Index BBh)",
    "Internal pull-up enable (Index BCh)": "内部上拉 (Index BCh)",
    "Internal pull-up enable (Index BDh)": "内部上拉 (Index BDh)",
    "Simple I/O enable (Index C0h)": "Simple I/O (Index C0h)",
    "Simple I/O enable (Index C1h)": "Simple I/O (Index C1h)",
    "Simple I/O enable (Index C2h)": "Simple I/O (Index C2h)",
    "Simple I/O enable (Index C3h)": "Simple I/O (Index C3h)",
    "Simple I/O enable (Index C4h)": "Simple I/O (Index C4h)",
    "Output/Input selection (Index C8h)": "方向控制 (Index C8h)",
    "Output/Input selection (Index C9h)": "方向控制 (Index C9h)",
    "Output/Input selection (Index CAh)": "方向控制 (Index CAh)",
    "Output/Input selection (Index CBh)": "方向控制 (Index CBh)",
    "Output/Input selection (Index CCh)": "方向控制 (Index CCh)",
    "Output/Input selection (Index CDh)": "方向控制 (Index CDh)",
    "Pad power": "Pad 渚涚數",
    "Global Register Index 25h<bit0-7>": "澶氬姛鑳介€夋嫨 (Index 25h)",
    "Global Register Index 26h<bit0-7>": "澶氬姛鑳介€夋嫨 (Index 26h)",
    "Global Register Index 27h<bit0-7>": "澶氬姛鑳介€夋嫨 (Index 27h)",
    "Global Register Index 28h<bit0-7>": "澶氬姛鑳介€夋嫨 (Index 28h)",
    "Global Register Index 29h<bit0-7>": "澶氬姛鑳介€夋嫨 (Index 29h)",
    "Internal Pull-up Enable (Index B8h)": "鍐呴儴涓婃媺 (Index B8h)",
    "Internal Pull-up Enable (Index B9h)": "鍐呴儴涓婃媺 (Index B9h)",
    "Internal Pull-up Enable (Index BAh)": "鍐呴儴涓婃媺 (Index BAh)",
    "Internal Pull-up Enable (Index BBh)": "鍐呴儴涓婃媺 (Index BBh)",
    "Internal Pull-up Enable (Index BCh)": "鍐呴儴涓婃媺 (Index BCh)",
    "Internal Pull-up Enable (Index BDh)": "鍐呴儴涓婃媺 (Index BDh)",
    "Simple I/O Enable (Index C0h)": "Simple I/O (Index C0h)",
    "Simple I/O Enable (Index C1h)": "Simple I/O (Index C1h)",
    "Simple I/O Enable (Index C2h)": "Simple I/O (Index C2h)",
    "Simple I/O Enable (Index C3h)": "Simple I/O (Index C3h)",
    "Simple I/O Enable (Index C4h)": "Simple I/O (Index C4h)",
    "Output/Input Selection (Index C8h)": "鏂瑰悜鎺у埗 (Index C8h)",
    "Output/Input Selection (Index C9h)": "鏂瑰悜鎺у埗 (Index C9h)",
    "Output/Input Selection (Index CAh)": "鏂瑰悜鎺у埗 (Index CAh)",
    "Output/Input Selection (Index CBh)": "鏂瑰悜鎺у埗 (Index CBh)",
    "Output/Input Selection (Index CCh)": "鏂瑰悜鎺у埗 (Index CCh)",
    "Output/Input Selection (Index CDh)": "鏂瑰悜鎺у埗 (Index CDh)",
}


def _clean_ite_table_cell(value: str | None) -> str:
    if value is None:
        return ""
    text = str(value).replace("\xa0", " ").replace("_", " ")
    text = text.replace("\r", " ").replace("\n", " ")
    text = text.replace("–", "-").replace("—", "-")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _normalize_ite_signal_label(text: str) -> str:
    cleaned = _clean_ite_table_cell(text)
    if not cleaned:
        return ""
    parts = []
    for part in cleaned.split("/"):
        token = part.strip(" ,;")
        if not token:
            continue
        token = token.replace(" #", "#").replace("# ", "#")
        token = token.replace("( ", "(").replace(" )", ")")
        token = re.sub(r"\s+", "_", token)
        token = token.replace("VLDT12", "VLDT_12")
        token = re.sub(
            r"^[ADFINEOT]_(?=(?:GP|FAN|PCH|CPU|VIN|TMPIN|VLDT|SUS|JP|IO80|CTS|RI|DCD|DSR|RTS|SIN|SOUT|PECI|SBTSI|PCIRST|THERMTRIP|ATXPG|PWR|LAD|LRESET|SERIRQ|LFRAME|PCICLK|KCLK|KDAT|VCORE|VCCBT|3VSB|5VDUAL|5VSB|MDAT|MCLK|GNDA|GNDD))",
            "",
            token,
        )
        token = re.sub(r"_+", "_", token).strip("_")
        parts.append(token)
    return "/".join(parts)


def _clean_ite_description(text: str) -> str:
    cleaned = _clean_ite_table_cell(text)
    if not cleaned:
        return ""
    cleaned = re.sub(r"^(?:[A-Z]\s+){1,4}(?=[A-Z0-9#])", "", cleaned)
    cleaned = cleaned.replace("Systme", "System")
    cleaned = cleaned.replace("signal form", "signal from")
    cleaned = cleaned.replace("Amplitude Fan Tachometer Input..", "Amplitude Fan Tachometer Input.")
    return cleaned.strip()


def _extract_ite_attribute(text: str) -> str:
    cleaned = _clean_ite_table_cell(text).upper().replace(" ", "")
    if not cleaned:
        return ""
    if cleaned == "DIDIOD8":
        return "DI"
    for attribute in IT8613_KNOWN_ATTRIBUTES:
        if cleaned == attribute or cleaned.startswith(attribute) or cleaned.endswith(attribute):
            return attribute
    for attribute in IT8613_KNOWN_ATTRIBUTES:
        if attribute in cleaned:
            return attribute
    return _clean_ite_table_cell(text)


def _extract_ite_pin_text(text: str) -> str:
    matches = re.findall(r"\d+(?:-\d+)?", _clean_ite_table_cell(text))
    return ",".join(matches)


def _it8613_side(pin_number: int) -> tuple[str, int]:
    if 1 <= pin_number <= 16:
        return "left", pin_number - 1
    if 17 <= pin_number <= 32:
        return "bottom", pin_number - 17
    if 33 <= pin_number <= 48:
        return "right", 48 - pin_number
    if 49 <= pin_number <= 64:
        return "top", 64 - pin_number
    raise ValueError(f"Unsupported IT8613 pin number: {pin_number}")


def _ite_lqfp_side(pin_number: int, pin_count: int) -> tuple[str, int]:
    quarter = pin_count // 4
    if 1 <= pin_number <= quarter:
        return "left", pin_number - 1
    if quarter < pin_number <= quarter * 2:
        return "bottom", pin_number - quarter - 1
    if quarter * 2 < pin_number <= quarter * 3:
        return "right", quarter * 3 - pin_number
    if quarter * 3 < pin_number <= pin_count:
        return "top", pin_count - pin_number
    raise ValueError(f"Unsupported ITE pin number: {pin_number} / {pin_count}")


def parse_ite_numeric_pin_table(pdf_path: Path, pin_table_page: int, pin_count: int) -> list[dict]:
    doc = fitz.open(pdf_path)
    try:
        page = doc.load_page(pin_table_page - 1)
        rows = None
        for table in page.find_tables(strategy="lines_strict").tables:
            extracted = table.extract()
            if not extracted or not extracted[0]:
                continue
            header = [_clean_ite_table_cell(cell) for cell in extracted[0]]
            if header[:2] == ["Pin", "Signal"] and len(header) >= 8:
                rows = extracted
                break
        if rows is None:
            raise RuntimeError(f"Failed to locate numeric pin table on page {pin_table_page} for {pdf_path.name}.")
    finally:
        doc.close()

    pins: list[dict] = []
    for row in rows[1:]:
        for index in range(0, min(len(row), 8), 2):
            pin_text = _extract_ite_pin_text(row[index] if index < len(row) else "")
            signal_text = _normalize_ite_signal_label(row[index + 1] if index + 1 < len(row) else "")
            if not pin_text or not signal_text:
                continue
            pin_number = int(pin_text.split(",")[0])
            side, side_index = _ite_lqfp_side(pin_number, pin_count)
            pins.append(_pin_record(pin_number, side, side_index, signal_text))

    pins = sorted(pins, key=lambda pin: pin["pin_number"])
    if len(pins) != pin_count or [pin["pin_number"] for pin in pins] != list(range(1, pin_count + 1)):
        raise RuntimeError(f"Failed to parse {pdf_path.name} top-view pins: parsed {len(pins)} entries, expected {pin_count}.")
    return pins


def parse_it8613_top_view(pdf_path: Path) -> list[dict]:
    doc = fitz.open(pdf_path)
    try:
        page = doc.load_page(IT8613_PIN_TABLE_PAGE - 1)
        tables = page.find_tables(strategy="lines_strict")
        if not tables.tables:
            raise RuntimeError("Failed to locate IT8613 numeric pin table.")
        rows = tables.tables[0].extract()
    finally:
        doc.close()

    pins: list[dict] = []
    for row in rows[1:]:
        for index in range(0, min(len(row), 8), 2):
            pin_text = _extract_ite_pin_text(row[index] if index < len(row) else "")
            signal_text = _normalize_ite_signal_label(row[index + 1] if index + 1 < len(row) else "")
            if not pin_text or not signal_text:
                continue
            pin_number = int(pin_text.split(",")[0])
            side, side_index = _it8613_side(pin_number)
            pins.append(_pin_record(pin_number, side, side_index, signal_text))

    pins = sorted(pins, key=lambda pin: pin["pin_number"])
    if len(pins) != 64 or [pin["pin_number"] for pin in pins] != list(range(1, 65)):
        raise RuntimeError(f"Failed to parse IT8613 top-view pins: parsed {len(pins)} entries")
    return pins


def _extract_ite_table_titles(page: fitz.Page) -> list[str]:
    titles = []
    for line in page.get_text("text").splitlines():
        text = _normalize_text(line)
        if text.startswith("Table 5-"):
            titles.append(text)
    return titles


def _assign_ite_table_titles(previous_title: str, titles: list[str], table_count: int) -> list[str]:
    if table_count <= 0:
        return []
    if not titles:
        return [previous_title] * table_count
    if len(titles) >= table_count:
        return titles[:table_count]
    continuation_count = table_count - len(titles)
    assigned = [previous_title] * continuation_count + titles
    if len(assigned) < table_count:
        assigned.extend([titles[-1]] * (table_count - len(assigned)))
    return assigned


def parse_ite_pin_descriptions(pdf_path: Path, page_numbers: range | list[int]) -> list[dict]:
    doc = fitz.open(pdf_path)
    try:
        details: list[dict] = []
        seen: set[tuple[str, str, str, str]] = set()
        seen_signal_keys: set[tuple[str, str]] = set()
        current_title = ""

        for page_no in page_numbers:
            page = doc.load_page(page_no - 1)
            titles = _extract_ite_table_titles(page)
            extracted_tables = []
            for table in page.find_tables(strategy="lines_strict").tables:
                rows = table.extract()
                if rows and rows[0] and any("Pin(s) No." in str(cell or "") for cell in rows[0]):
                    current_pin_text = ""
                    table_keys: set[tuple[str, str]] = set()
                    for row in rows[1:]:
                        row = list(row) + [""] * 6
                        pin_text = _extract_ite_pin_text(row[0])
                        if pin_text:
                            current_pin_text = pin_text
                        signal_text = _normalize_ite_signal_label(row[1])
                        if current_pin_text and signal_text:
                            table_keys.add((current_pin_text, signal_text))
                    if table_keys and seen_signal_keys and len(table_keys & seen_signal_keys) / len(table_keys) >= 0.75:
                        continue
                    extracted_tables.append(rows)
            if not extracted_tables:
                continue

            assigned_titles = _assign_ite_table_titles(current_title, titles, len(extracted_tables))
            current_pin_text = ""

            for table_title, rows in zip(assigned_titles, extracted_tables):
                if table_title:
                    current_title = table_title
                interface = re.sub(r"^Table\s+[0-9\-]+\.\s*", "", current_title).strip()

                for row in rows[1:]:
                    row = list(row) + [""] * 6
                    pin_text = _extract_ite_pin_text(row[0])
                    if pin_text:
                        current_pin_text = pin_text
                    if not current_pin_text:
                        continue

                    signal_text = _normalize_ite_signal_label(row[1])
                    if not signal_text:
                        continue

                    attribute = _extract_ite_attribute(row[2])
                    power = _clean_ite_table_cell(row[3])
                    description = _clean_ite_description(next((cell for cell in row[4:] if _clean_ite_table_cell(cell)), ""))
                    summary = description.split(". ")[0].strip() if description else signal_text
                    entry = {
                        "page": page_no,
                        "table": current_title,
                        "table_cn": translate_table_label(current_title),
                        "interface": interface,
                        "interface_cn": translate_spec_text(interface),
                        "pin_text": current_pin_text,
                        "pin_numbers": expand_pin_numbers(current_pin_text),
                        "signal_text": signal_text,
                        "signals": expand_signal_aliases(signal_text),
                        "attribute": attribute,
                        "attribute_description": describe_attribute(attribute),
                        "power": power,
                        "summary": summary,
                        "summary_cn": translate_spec_text(summary),
                        "description": description,
                        "description_cn": translate_spec_text(description),
                    }
                    dedupe_key = (entry["table"], entry["pin_text"], entry["signal_text"], entry["description"])
                    if entry["pin_numbers"] and dedupe_key not in seen:
                        seen.add(dedupe_key)
                        seen_signal_keys.add((entry["pin_text"], entry["signal_text"]))
                        details.append(entry)
        return details
    finally:
        doc.close()


def parse_it8613_pin_descriptions(pdf_path: Path) -> list[dict]:
    return parse_ite_pin_descriptions(pdf_path, IT8613_PIN_DESCRIPTION_TABLE_PAGES)


def _normalize_ite_gpio_group(text: str) -> str:
    cleaned = _clean_ite_table_cell(text).replace(" ", "")
    match = re.search(r"(?:GPIO)?([0-9A-Z]+)x", cleaned, re.IGNORECASE)
    if match:
        return f"GPIO{match.group(1).upper()}x"
    return cleaned


def _normalize_ite_gpio_alt_header(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", _clean_ite_table_cell(text).lower())


def _normalize_ite_gpio_name(text: str) -> str:
    cleaned = _clean_ite_table_cell(text).replace(" ", "").upper()
    match = re.search(r"GP(?:IO|O)?([A-Z]?\d+)", cleaned, re.IGNORECASE)
    if not match:
        return ""
    return f"GPIO{match.group(1).upper()}"


def _resolve_ite_gpio_pin_number(record: dict, alias_to_pins: dict[str, set[int]]) -> int | None:
    preferred: list[int] = []
    fallback: list[int] = []
    for index in range(1, 6):
        for alias in split_aliases(record.get(f"func{index}", "")):
            if not alias:
                continue
            matches = sorted(alias_to_pins.get(alias, set()))
            if len(matches) != 1:
                continue
            if re.fullmatch(r"GP(?:O)?[A-Z]?\d+", alias, re.IGNORECASE):
                fallback.extend(matches)
            else:
                preferred.extend(matches)
    for candidates in (preferred, fallback):
        if candidates and len(set(candidates)) == 1:
            return candidates[0]
    return None


def parse_ite_gpio_alt_functions(pdf_path: Path, page_numbers: range | list[int], pins: list[dict]) -> dict[int, dict]:
    alias_to_pins: dict[str, set[int]] = defaultdict(set)
    for pin in pins:
        for alias in pin.get("aliases", []):
            alias_to_pins[alias].add(pin["pin_number"])

    doc = fitz.open(pdf_path)
    try:
        rows: dict[int, dict] = {}
        for page_no in page_numbers:
            page = doc.load_page(page_no - 1)
            for table in page.find_tables(strategy="lines_strict").tables:
                extracted = table.extract()
                if not extracted or not extracted[0]:
                    continue
                headers = [_normalize_ite_gpio_alt_header(cell) for cell in extracted[0]]
                if not any("func" in header for header in headers):
                    continue

                group_index = next((index for index, header in enumerate(headers) if header == "group"), None)
                bit_index = next((index for index, header in enumerate(headers) if header == "bit"), None)
                pin_index = next((index for index, header in enumerate(headers) if header in {"pinloc", "pin"}), None)
                func_indexes = [index for index, header in enumerate(headers) if "func" in header]
                cond_indexes = [index for index, header in enumerate(headers) if "condition" in header]
                if group_index is None or bit_index is None or not func_indexes:
                    continue

                current_group = ""
                for row in extracted[1:]:
                    row = list(row) + [""] * max(0, len(headers) + 4 - len(row))
                    group = _normalize_ite_gpio_group(row[group_index]) if group_index < len(row) else ""
                    if group:
                        current_group = group

                    record = {
                        "page": page_no,
                        "group": current_group,
                        "bit": _clean_ite_table_cell(row[bit_index]) if bit_index < len(row) else "",
                    }
                    if not record["bit"]:
                        continue

                    pin_number = None
                    if pin_index is not None and pin_index < len(row):
                        pin_text = _extract_ite_pin_text(row[pin_index])
                        if pin_text:
                            pin_number = int(pin_text.split(",")[0])

                    for func_pos, func_index in enumerate(func_indexes[:5], start=1):
                        func_text = re.sub(r"\([^)]*\)", "", _clean_ite_table_cell(row[func_index] if func_index < len(row) else ""))
                        normalized_func = _normalize_ite_signal_label(func_text)
                        if len(normalized_func) == 1 and normalized_func.isalpha():
                            normalized_func = ""
                        record[f"func{func_pos}"] = normalized_func
                        next_func_index = func_indexes[func_pos] if func_pos < len(func_indexes) else None
                        cond_index = next(
                            (
                                index
                                for index in cond_indexes
                                if index > func_index and (next_func_index is None or index < next_func_index)
                            ),
                            None,
                        )
                        record[f"cond{func_pos}"] = (
                            _clean_ite_table_cell(row[cond_index] if cond_index is not None and cond_index < len(row) else "")
                            if normalized_func
                            else ""
                        )

                    if pin_number is None:
                        pin_number = _resolve_ite_gpio_pin_number(record, alias_to_pins)
                    if pin_number is None:
                        continue
                    record["pin_number"] = pin_number
                    rows[pin_number] = record
        return rows
    finally:
        doc.close()


def parse_it8613_gpio_alt_functions(pdf_path: Path) -> dict[int, dict]:
    pins = parse_it8613_top_view(pdf_path)
    return parse_ite_gpio_alt_functions(pdf_path, IT8613_GPIO_ALT_TABLE_PAGES, pins)


def _normalize_ite_gpio_header(text: str) -> str:
    normalized = _normalize_ite_gpio_name(text)
    if not normalized:
        return ""
    match = re.fullmatch(r"GPIO(\d+)", normalized)
    if match:
        return f"GPIO{int(match.group(1)):02d}"
    return normalized


def _normalize_ite_gpio_reg_value(text: str) -> str:
    cleaned = _clean_ite_table_cell(text)
    if not cleaned:
        return ""
    replacements = {
        "§°": "O",
        "§·": "X",
        "Ðž": "O",
        "Ð¥": "X",
        "งฐ": "O",
        "งท": "X",
        "О": "O",
        "Х": "X",
    }
    for source, target in replacements.items():
        cleaned = cleaned.replace(source, target)
    cleaned = cleaned.replace("*Note1", "").replace("*Note4", "")
    cleaned = cleaned.replace("ï€", " ").replace("", " ")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def parse_ite_gpio_registers(pdf_path: Path, page_numbers: range | list[int]) -> dict[str, dict]:
    doc = fitz.open(pdf_path)
    try:
        gpio_rows: dict[str, dict] = {}
        current_group = ""
        current_headers: dict[int, str] = {}

        for page_no in page_numbers:
            page = doc.load_page(page_no - 1)
            for table in page.find_tables(strategy="lines_strict").tables:
                extracted = table.extract()
                for row in extracted:
                    row = list(row) + [""] * 16
                    first = _clean_ite_table_cell(row[0])
                    if first.startswith("GP I/O Group"):
                        current_group = first
                        current_headers = {}
                        for index, cell in enumerate(row[1:], start=1):
                            gpio_name = _normalize_ite_gpio_header(cell)
                            if gpio_name:
                                current_headers[index] = gpio_name
                                gpio_rows.setdefault(gpio_name, {"page": page_no, "group": current_group})
                        continue
                    if not current_headers or not first or first.startswith("Note:"):
                        continue
                    property_name = first
                    for index, gpio_name in current_headers.items():
                        value = _normalize_ite_gpio_reg_value(row[index] if index < len(row) else "")
                        if not value:
                            continue
                        gpio_rows.setdefault(gpio_name, {"page": page_no, "group": current_group})
                        gpio_rows[gpio_name][property_name] = value
        return gpio_rows
    finally:
        doc.close()


def parse_it8613_gpio_registers(pdf_path: Path) -> dict[str, dict]:
    return parse_ite_gpio_registers(pdf_path, range(IT8613_GPIO_REG_TABLE_PAGE, IT8613_GPIO_REG_TABLE_PAGE + 1))


def _it8613_gpio_key(pin: dict) -> str:
    for alias in pin.get("aliases", []):
        gpio_name = _normalize_ite_gpio_name(alias)
        if gpio_name:
            return gpio_name
    return ""


def _translate_it8613_gpio_property(property_name: str) -> str:
    return IT8613_GPIO_PROPERTY_LABELS.get(property_name, property_name)


def _it8613_generic_info_rows(pin: dict, gpio_alt_info: dict | None, gpio_reg_info: dict | None) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    gpio_key = _it8613_gpio_key(pin)
    if gpio_alt_info:
        rows.extend(
            [
                ("GPIO 组", gpio_alt_info.get("group", "")),
                ("GPIO 位", gpio_alt_info.get("bit", "")),
                ("GPIO 编号", gpio_key or "-"),
            ]
        )
        for index in range(1, 6):
            func = gpio_alt_info.get(f"func{index}", "")
            cond = gpio_alt_info.get(f"cond{index}", "")
            if func:
                rows.append((f"功能 {index}", func))
            if cond:
                rows.append((f"条件 {index}", cond))
    if gpio_reg_info:
        for key, value in gpio_reg_info.items():
            if key in {"page", "group"} or not value:
                continue
            rows.append((_translate_it8613_gpio_property(key), value))
    deduped: list[tuple[str, str]] = []
    seen = set()
    for title, value in rows:
        if value is None or not str(value).strip():
            continue
        pair = (title, str(value).strip())
        if pair in seen:
            continue
        seen.add(pair)
        deduped.append(pair)
    return deduped


def _it8613_voltage_profile(pin: dict, detail_entries: list[dict]) -> dict:
    aliases = set(pin.get("aliases", []))
    attributes = {detail.get("attribute", "") for detail in detail_entries if detail.get("attribute")}
    supports_1_8v = False
    supports_3_3v = True
    supports_1_8v_input_only = False
    supports_5v_tolerant = False
    notes: list[str] = []

    if aliases == {"VCORE"}:
        supports_1_8v = True
        supports_3_3v = False
        notes.append("VCORE 为芯片内部 1.8V 电源输出。")
    elif aliases == {"VCCBT"}:
        supports_1_8v = True
        supports_3_3v = False
        notes.append("VCCBT 是 Bay Trail 平台 SERIRQ 的 1.8V 供电。")

    if aliases & IT8613_SPECIAL_1V8_INPUT_ALIASES:
        supports_1_8v = True
        supports_1_8v_input_only = True
        notes.append("JP3 可将该组输入阈值切换为 1.8V。")

    if aliases & IT8613_LPC_ALIASES:
        supports_3_3v = True
        supports_5v_tolerant = False
        notes.append("LPC 接口引脚为 3.3V only。")

    if any(alias.startswith("VIN") or alias.startswith("TMPIN") or alias == "VREF" for alias in aliases):
        supports_3_3v = True
        supports_5v_tolerant = False
        notes.append("硬件监控模拟引脚为 3.3V only。")

    if any(attribute in IT8613_INPUT_ATTRIBUTES for attribute in attributes) and not (aliases & IT8613_LPC_ALIASES):
        supports_5v_tolerant = True
        notes.append("输入路径支持 5V tolerance；若工作在输出模式，不应直接上拉到 5V。")

    if any(attribute in IT8613_OUTPUT_ATTRIBUTES for attribute in attributes):
        notes.append("输出型引脚不应直接上拉到 5V。")

    notes = list(dict.fromkeys(notes))

    if supports_1_8v_input_only and supports_3_3v:
        summary = "支持 3.3V；特定模式下可切换为 1.8V 输入阈值。"
    elif supports_1_8v and not supports_3_3v:
        summary = "主要为 1.8V 电源/信号。"
    elif supports_3_3v:
        summary = "支持 3.3V 工作。"
    else:
        summary = "PDF 中未解析到明确的 1.8V / 3.3V 说明。"

    return {
        "supports_1_8v": supports_1_8v,
        "supports_3_3v": supports_3_3v,
        "supports_1_8v_input_only": supports_1_8v_input_only,
        "supports_5v_tolerant": supports_5v_tolerant,
        "summary": summary,
        "notes": notes,
    }


def _translate_ite_gpio_property(property_name: str) -> str:
    return IT8613_GPIO_PROPERTY_LABELS.get(property_name, property_name)


def _ite_superio_generic_info_rows(pin: dict, gpio_alt_info: dict | None, gpio_reg_info: dict | None) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    gpio_key = _it8613_gpio_key(pin)
    if gpio_alt_info:
        rows.extend(
            [
                ("GPIO 缁?", gpio_alt_info.get("group", "")),
                ("GPIO 浣?", gpio_alt_info.get("bit", "")),
                ("GPIO 缂栧彿", gpio_key or "-"),
            ]
        )
        for index in range(1, 6):
            func = gpio_alt_info.get(f"func{index}", "")
            cond = gpio_alt_info.get(f"cond{index}", "")
            if func:
                rows.append((f"鍔熻兘 {index}", func))
            if cond:
                rows.append((f"鏉′欢 {index}", cond))
    if gpio_reg_info:
        for key, value in gpio_reg_info.items():
            if key in {"page", "group"} or not value:
                continue
            rows.append((_translate_ite_gpio_property(key), value))
    deduped: list[tuple[str, str]] = []
    seen = set()
    for title, value in rows:
        if value is None or not str(value).strip():
            continue
        pair = (title, str(value).strip())
        if pair in seen:
            continue
        seen.add(pair)
        deduped.append(pair)
    return deduped


def _ite_superio_voltage_profile(pin: dict, detail_entries: list[dict], gpio_alt_info: dict | None) -> dict:
    profile = _voltage_profile(pin, detail_entries, gpio_alt_info)
    aliases = set(pin.get("aliases", []))
    attributes = {detail.get("attribute", "") for detail in detail_entries if detail.get("attribute")}
    detail_text = " ".join(
        " ".join(
            [
                detail.get("interface", ""),
                detail.get("summary", ""),
                detail.get("description", ""),
                detail.get("power", ""),
            ]
        )
        for detail in detail_entries
    )

    notes = list(profile.get("notes", []))
    supports_1_8v = profile["supports_1_8v"]
    supports_3_3v = profile["supports_3_3v"]
    supports_1_8v_input_only = profile["supports_1_8v_input_only"]
    supports_5v_tolerant = profile["supports_5v_tolerant"]

    if not supports_1_8v and ("1.8V" in detail_text or attributes & {"DI-L", "DIOD8-L"}):
        supports_1_8v = True
    if not supports_3_3v and (attributes - {"PWR", "GND"} or gpio_alt_info is not None):
        supports_3_3v = True
    if not supports_1_8v and any(re.search(r"(?:^|[^0-9])1V8(?:[^0-9]|$)|1\\.8V", alias, re.IGNORECASE) for alias in aliases):
        supports_1_8v = True
    if not supports_3_3v and any(re.search(r"(?:^|[^0-9])3V(?:[^0-9]|$)|3\\.3V|VCC|VSB", alias, re.IGNORECASE) for alias in aliases):
        supports_3_3v = True
    if not supports_5v_tolerant and "5V" in detail_text:
        supports_5v_tolerant = True
    if not supports_1_8v_input_only and (attributes & {"DI-L"}):
        supports_1_8v_input_only = True

    if supports_1_8v and supports_3_3v and supports_1_8v_input_only:
        summary = "鏀寔 3.3V锛涢儴鍒嗘ā寮忔垨 GPIO 杈撳叆鏀寔 1.8V銆?"
    elif supports_1_8v and supports_3_3v:
        summary = "鍚屾椂鏀寔 1.8V 鍜?3.3V 宸ヤ綔銆?"
    elif supports_1_8v:
        summary = "鏀寔 1.8V 宸ヤ綔銆?"
    elif supports_3_3v:
        summary = "鏀寔 3.3V 宸ヤ綔銆?"
    else:
        summary = "PDF 涓湭瑙ｆ瀽鍒版槑纭殑 1.8V / 3.3V 璇存槑銆?"

    return {
        "supports_1_8v": supports_1_8v,
        "supports_3_3v": supports_3_3v,
        "supports_1_8v_input_only": supports_1_8v_input_only,
        "supports_5v_tolerant": supports_5v_tolerant,
        "summary": summary,
        "notes": list(dict.fromkeys(notes)),
    }


def _apply_ite_superio_gpio_aliases(pin: dict, gpio_alt_info: dict | None) -> None:
    if not gpio_alt_info:
        return
    extra_aliases = [gpio_alt_info.get(f"func{index}", "") for index in range(1, 6)]
    pin["aliases"] = list(dict.fromkeys(pin["aliases"] + [alias for alias in extra_aliases if alias]))
    pin["label"] = "/".join(pin["aliases"])
    pin["display_name"] = pin["aliases"][0] if pin["aliases"] else pin["label"]
    pin["modules"] = classify_aliases(pin["aliases"])
    pin["primary_module"] = primary_module(pin["aliases"])


def build_ite_superio_chip(config: dict, pdf_path: Path) -> dict:
    pins = parse_ite_numeric_pin_table(pdf_path, config["pin_table_page"], config["pin_count"])
    pin_detail_rows = parse_ite_pin_descriptions(pdf_path, config["pin_description_pages"])
    pin_detail_map = _build_pin_detail_map(pin_detail_rows)
    gpio_alt_map = parse_ite_gpio_alt_functions(pdf_path, config["gpio_alt_pages"], pins)
    gpio_reg_map = parse_ite_gpio_registers(pdf_path, config["gpio_reg_pages"])

    for pin in pins:
        detail_entries = pin_detail_map.get(pin["pin_number"], [])
        gpio_alt_info = gpio_alt_map.get(pin["pin_number"])
        _apply_ite_superio_gpio_aliases(pin, gpio_alt_info)
        gpio_reg_info = gpio_reg_map.get(_it8613_gpio_key(pin), {})
        voltage_profile = _ite_superio_voltage_profile(pin, detail_entries, gpio_alt_info)
        pin["detail_entries"] = detail_entries
        pin["gpio_alt_info"] = gpio_alt_info
        pin["generic_info_rows"] = _ite_superio_generic_info_rows(pin, gpio_alt_info, gpio_reg_info)
        pin["voltage_profile"] = voltage_profile
        pin["supports_1_8v"] = voltage_profile["supports_1_8v"]
        pin["supports_3_3v"] = voltage_profile["supports_3_3v"]
        pin["supports_1_8v_input_only"] = voltage_profile["supports_1_8v_input_only"]
        pin["supports_5v_tolerant"] = voltage_profile["supports_5v_tolerant"]

    modules = build_module_index(pins)
    signals = build_signal_index(pins)
    return {
        "chip_id": config["chip_id"],
        "vendor": config["vendor"],
        "model": config["model"],
        "display_name": config["display_name"],
        "category": config["category"],
        "family": config["family"],
        "series": config["series"],
        "chip_role": config["chip_role"],
        "variants": config["variants"],
        "package": config["package"],
        "package_type": config["package_type"],
        "view_type": "package_top",
        "document_type": config["document_type"],
        "description": config["description"],
        "features": config["features"],
        "pin_count": len(pins),
        "source_pdf": str(pdf_path),
        "source_pdf_name": pdf_path.name,
        "sections": extract_top_sections(pdf_path),
        "modules": modules,
        "signals": signals,
        "pins": pins,
        "notes": [
            "灏佽鍥句緷鎹?Pin Configuration / Pins Listed in Numeric Order 琛ㄦ牸鐢熸垚銆?",
            "寮曡剼璇︽儏鏉ヨ嚜 Pin Description 绔犺妭锛孏PIO 澶氬姛鑳戒笌瀵勫瓨鍣ㄤ俊鎭潵鑷?List of GPIO Pins銆?",
            f"当前模块覆盖重点：{', '.join(top_module_names(modules))}。",
        ],
    }


def build_it8625_chip(pdf_path: Path) -> dict:
    return build_ite_superio_chip(ITE_SUPERIO_CONFIGS["it8625_l"], pdf_path)


def build_it8728_chip(pdf_path: Path) -> dict:
    return build_ite_superio_chip(ITE_SUPERIO_CONFIGS["it8728_f"], pdf_path)


def build_it8772_chip(pdf_path: Path) -> dict:
    return build_ite_superio_chip(ITE_SUPERIO_CONFIGS["it8772_f"], pdf_path)


def build_it8786_chip(pdf_path: Path) -> dict:
    return build_ite_superio_chip(ITE_SUPERIO_CONFIGS["it8786_h"], pdf_path)


def build_it8613_chip(pdf_path: Path) -> dict:
    pins = parse_it8613_top_view(pdf_path)
    pin_detail_rows = parse_it8613_pin_descriptions(pdf_path)
    pin_detail_map = _build_pin_detail_map(pin_detail_rows)
    gpio_alt_map = parse_it8613_gpio_alt_functions(pdf_path)
    gpio_reg_map = parse_it8613_gpio_registers(pdf_path)

    for pin in pins:
        detail_entries = pin_detail_map.get(pin["pin_number"], [])
        gpio_alt_info = gpio_alt_map.get(pin["pin_number"])
        gpio_reg_info = gpio_reg_map.get(_it8613_gpio_key(pin), {})
        if gpio_alt_info:
            extra_aliases = [gpio_alt_info.get(f"func{index}", "") for index in range(1, 6)]
            pin["aliases"] = list(dict.fromkeys(pin["aliases"] + [alias for alias in extra_aliases if alias]))
            pin["label"] = "/".join(pin["aliases"])
            pin["display_name"] = pin["aliases"][0] if pin["aliases"] else pin["label"]
            pin["modules"] = classify_aliases(pin["aliases"])
            pin["primary_module"] = primary_module(pin["aliases"])
        voltage_profile = _it8613_voltage_profile(pin, detail_entries)
        pin["detail_entries"] = detail_entries
        pin["gpio_alt_info"] = gpio_alt_info
        pin["generic_info_rows"] = _it8613_generic_info_rows(pin, gpio_alt_info, gpio_reg_info)
        pin["voltage_profile"] = voltage_profile
        pin["supports_1_8v"] = voltage_profile["supports_1_8v"]
        pin["supports_3_3v"] = voltage_profile["supports_3_3v"]
        pin["supports_1_8v_input_only"] = voltage_profile["supports_1_8v_input_only"]
        pin["supports_5v_tolerant"] = voltage_profile["supports_5v_tolerant"]

    modules = build_module_index(pins)
    signals = build_signal_index(pins)
    return {
        "chip_id": "it8613_e",
        "vendor": "ITE",
        "model": "IT8613E V0.3",
        "display_name": "IT8613E / IT8613EX",
        "category": "Super I/O / HWM",
        "family": "IT8613",
        "series": "IT86xx",
        "chip_role": "Super I/O Controller",
        "variants": ["IT8613E", "IT8613EX"],
        "package": "LQFP-64L",
        "package_type": "LQFP",
        "view_type": "package_top",
        "document_type": "Datasheet",
        "description": "ITE Super I/O 芯片封装库，包含 64-LQFP 引脚定义、GPIO 复用、GPIO 电源/寄存器能力和主要控制信号说明。",
        "features": [
            "支持查看串口、LPC、风扇控制、硬件监控、PCH / SMBus 等接口",
            "支持显示 GPIO 复用条件、S3/S5 控制、内部上拉和方向控制",
            "支持显示 3.3V、部分 1.8V 输入阈值与 5V tolerance 说明",
        ],
        "pin_count": len(pins),
        "source_pdf": str(pdf_path),
        "source_pdf_name": pdf_path.name,
        "sections": extract_top_sections(pdf_path),
        "modules": modules,
        "signals": signals,
        "pins": pins,
        "notes": [
            "封装图依据第 4 章 Pin Configuration 与 Pins Listed in Numeric Order 生成。",
            "引脚说明详情来自第 5 章 Pin Description 表格。",
            "GPIO 复用与寄存器能力来自第 6 章 List of GPIO Pins。",
            "IT8613E 为 3.3V 芯片；部分输入阈值可通过 JP3 切到 1.8V。",
            f"当前模块覆盖重点：{', '.join(top_module_names(modules))}。",
        ],
    }


def _clean_amd_compact_cell(value: str | None) -> str:
    if value is None:
        return ""
    return value.replace("\xa0", " ").replace("\n", "").replace(" ", "").strip()


def _clean_amd_bank_cell(value: str | None) -> str:
    if value is None:
        return ""
    text = re.sub(r"\s+", "_", value.replace("\xa0", " "))
    return re.sub(r"_+", "_", text).strip("_")


def _extract_amd_pad_alias(*values: str) -> str:
    for value in values:
        match = re.search(r"(?:A|E)?GPIO\d+", value.upper())
        if match:
            return match.group(0)
    return ""


def _normalize_amd_alias(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_\[\]/#]+", "", value.upper()).strip("_/")
    if not cleaned:
        return ""
    if cleaned in {"NA", "N/A"}:
        return "n/a"

    squashed = cleaned.replace("_", "").replace("[", "").replace("]", "")
    canonical_patterns = [
        (r"^(A|E)?GPIO(\d+)$", lambda m: f"{m.group(1) or ''}GPIO{int(m.group(2))}"),
        (r"^GPIO(\d+)$", lambda m: f"GPIO{int(m.group(1))}"),
        (r"^UART(\d)(CTSL|RTSL|RXD|TXD|INTR)$", lambda m: f"UART{m.group(1)}_{'CTS_L' if m.group(2) == 'CTSL' else 'RTS_L' if m.group(2) == 'RTSL' else m.group(2)}"),
        (r"^I2C(\d)(SCL|SDA)$", lambda m: f"I2C{m.group(1)}_{m.group(2)}"),
        (r"^I3C(\d)(SCL|SDA)$", lambda m: f"I3C{m.group(1)}_{m.group(2)}"),
        (r"^SMBUS(\d)(SCL|SDA)$", lambda m: f"SMBUS{m.group(1)}_{m.group(2)}"),
        (r"^SPI(\d)CLK$", lambda m: f"SPI{m.group(1)}_CLK"),
        (r"^SPI(\d)DAT(\d)$", lambda m: f"SPI{m.group(1)}_DAT{m.group(2)}"),
        (r"^SPI(\d)CS(\d)L$", lambda m: f"SPI{m.group(1)}_CS{m.group(2)}_L"),
        (r"^SPIROM(REQ|GNT)$", lambda m: f"SPI_ROM_{m.group(1)}"),
        (r"^SPITPMCSL$", lambda _m: "SPI_TPM_CS_L"),
        (r"^ESPIRESETL$", lambda _m: "ESPI_RESET_L"),
        (r"^ESPIALERTL$", lambda _m: "ESPI_ALERT_L"),
        (r"^ESPIALERTD1$", lambda _m: "ESPI_ALERT_D1"),
        (r"^ESPICSL$", lambda _m: "ESPI_CS_L"),
        (r"^ESPICLK$", lambda _m: "ESPI_CLK"),
        (r"^ESPIDAT(\d)$", lambda m: f"ESPI_DAT[{m.group(1)}]"),
        (r"^PCIERST(\d*)L$", lambda m: f"PCIE_RST{m.group(1)}_L" if m.group(1) else "PCIE_RST_L"),
        (r"^CLKREQ(\d+)L$", lambda m: f"CLK_REQ{m.group(1)}_L"),
        (r"^USBOC(\d)L$", lambda m: f"USB_OC{m.group(1)}_L"),
        (r"^TMUCLKOUT(\d)$", lambda m: f"TMU_CLK_OUT{m.group(1)}"),
        (r"^DFVRCONTEXT(\d)$", lambda m: f"DF_VRCONTEXT_{m.group(1)}"),
        (r"^GFX10CACIPIO(\d)$", lambda m: f"GFX10_CAC_IPIO{m.group(1)}"),
        (r"^PSPINTR(\d)$", lambda m: f"PSP_INTR{m.group(1)}"),
        (r"^GENINT(\d)L$", lambda m: f"GENINT{m.group(1)}_L"),
        (r"^PWRBTNL$", lambda _m: "PWR_BTN_L"),
        (r"^SYSRESETL$", lambda _m: "SYS_RESET_L"),
        (r"^RSTSTRAP$", lambda _m: "RST_STRAP"),
        (r"^WAKEL$", lambda _m: "WAKE_L"),
        (r"^S0A3GPIO$", lambda _m: "S0A3_GPIO"),
        (r"^ACPRES$", lambda _m: "AC_PRES"),
        (r"^SHUTDOWNL$", lambda _m: "SHUTDOWN_L"),
        (r"^SPKR$", lambda _m: "SPKR"),
        (r"^BLINK$", lambda _m: "BLINK"),
        (r"^LLBL$", lambda _m: "LLB_L"),
        (r"^OSCIN$", lambda _m: "OSCIN"),
        (r"^PKGSTRAP(\d)$", lambda m: f"PKG_STRAP{m.group(1)}"),
        (r"^SD0CMD$", lambda _m: "SD0_CMD"),
        (r"^SD0CLK$", lambda _m: "SD0_CLK"),
        (r"^SD0DATA(\d)$", lambda m: f"SD0_DATA{m.group(1)}"),
    ]
    for pattern, replacer in canonical_patterns:
        match = re.fullmatch(pattern, squashed)
        if match:
            return replacer(match)

    fallback_fixups = {
        "SPIR_OMG_NT": "SPI_ROM_GNT",
        "SPIR_OMG_NT": "SPI_ROM_GNT",
        "SYS_RESETL_": "SYS_RESET_L",
        "WAKEL_": "WAKE_L",
        "SHUTDOWNL_": "SHUTDOWN_L",
        "SMBUS0SC_L": "SMBUS0_SCL",
        "SMBUS0SD_A": "SMBUS0_SDA",
        "SMBUS1SC_L": "SMBUS1_SCL",
        "SMBUS1SD_A": "SMBUS1_SDA",
        "I2C0SC_L": "I2C0_SCL",
        "I2C0SD_A": "I2C0_SDA",
        "I2C1SC_L": "I2C1_SCL",
        "I2C1SD_A": "I2C1_SDA",
        "I3C0SC_L": "I3C0_SCL",
        "I3C0SD_A": "I3C0_SDA",
        "I3C1SC_L": "I3C1_SCL",
        "I3C1SD_A": "I3C1_SDA",
    }
    if cleaned in fallback_fixups:
        return fallback_fixups[cleaned]
    return cleaned.strip("_")


def parse_amd_iomux_rows(pdf_path: Path) -> dict[int, dict]:
    doc = fitz.open(pdf_path)
    try:
        merged_rows: list[dict] = []
        current_row: dict | None = None
        for page_no in AMD_IOMUX_TABLE_PAGES:
            page = doc.load_page(page_no - 1)
            tables = page.find_tables().tables
            if not tables:
                continue
            for row in tables[0].extract():
                cells = [_clean_amd_compact_cell(cell) for cell in row]
                if not any(cells):
                    continue
                joined = "".join(cells)
                if "BumpPinName" in joined or "IOMUXFunctionTable" in joined:
                    continue

                first_cell = cells[0]
                is_new_row = first_cell.startswith("IOMUXx") or (first_cell == "IOMU" and cells[3].isdigit())
                if is_new_row:
                    current_row = {"page": page_no, "cells": cells}
                    merged_rows.append(current_row)
                    continue

                if current_row is None:
                    continue
                for index, value in enumerate(cells):
                    if value:
                        current_row["cells"][index] += value

        iomux_rows: dict[int, dict] = {}
        for row in merged_rows:
            cells = row["cells"]
            gpio_text = cells[3]
            if not gpio_text.isdigit():
                continue
            gpio_index = int(gpio_text)
            iomux_id = cells[0].replace("IOMU", "IOMUX")
            iomux_rows[gpio_index] = {
                "page": row["page"],
                "iomux_id": iomux_id,
                "bump_name": cells[1],
                "domain": cells[2],
                "gpio_index": gpio_index,
                "gevent": cells[4],
                "override_0": _normalize_amd_alias(cells[5]),
                "override_1": _normalize_amd_alias(cells[6]),
                "functions": [_normalize_amd_alias(cells[column]) for column in range(7, 11) if _normalize_amd_alias(cells[column])],
                "default_io_state": cells[11],
                "iomux_reset": cells[12],
            }
        return iomux_rows
    finally:
        doc.close()


def parse_amd_gpio_bank_rows(pdf_path: Path) -> dict[int, dict]:
    doc = fitz.open(pdf_path)
    try:
        bank_rows: dict[int, dict] = {}
        for page_no in AMD_GPIO_BANK_PAGES:
            page = doc.load_page(page_no - 1)
            for table in page.find_tables().tables:
                rows = table.extract()
                if not rows or len(rows[0]) != 4:
                    continue

                header = [_clean_amd_bank_cell(cell) for cell in rows[0]]
                if "Register" in header:
                    data_rows = rows[1:]
                elif rows[0][0] and str(rows[0][0]).startswith("GPIOx"):
                    data_rows = rows
                else:
                    continue

                for row in data_rows:
                    cells = [_clean_amd_bank_cell(cell) for cell in row]
                    if len(cells) != 4 or not cells[0].startswith("GPIOx") or not cells[2].isdigit():
                        continue
                    gpio_index = int(cells[2])
                    raw_name = cells[3]
                    if not raw_name.startswith("BP_"):
                        continue
                    bank_rows[gpio_index] = {
                        "page": page_no,
                        "register": cells[0],
                        "reset_value": cells[1],
                        "gpio_index": gpio_index,
                        "raw_name": raw_name,
                        "bank": gpio_index // 64,
                        "table_number": 155 + (gpio_index // 64),
                    }
        return bank_rows
    finally:
        doc.close()


def _assign_functional_package_sides(pins: list[dict]) -> None:
    side_order = ["left", "bottom", "right", "top"]
    base_count = len(pins) // 4
    extra = len(pins) % 4
    counts = [base_count + (1 if index < extra else 0) for index in range(4)]

    cursor = 0
    for side, count in zip(side_order, counts):
        for side_index in range(count):
            pins[cursor]["side"] = side
            pins[cursor]["side_index"] = side_index
            cursor += 1


def build_amd_57396_chip(pdf_path: Path) -> dict:
    iomux_rows = parse_amd_iomux_rows(pdf_path)
    bank_rows = parse_amd_gpio_bank_rows(pdf_path)

    shared_indexes = sorted(set(iomux_rows) & set(bank_rows))
    pins: list[dict] = []
    for pin_number, gpio_index in enumerate(shared_indexes, start=1):
        iomux = iomux_rows[gpio_index]
        bank = bank_rows[gpio_index]

        pad_alias = _extract_amd_pad_alias(bank["raw_name"], iomux["bump_name"]) or f"GPIO{gpio_index}"
        aliases: list[str] = []

        default_function = iomux["functions"][0] if iomux["functions"] else ""
        if default_function:
            aliases.append(default_function)
        if pad_alias and pad_alias not in aliases:
            aliases.append(pad_alias)

        for alias in iomux["functions"][1:] + [iomux["override_0"], iomux["override_1"]]:
            if alias and alias not in aliases and alias != "n/a":
                aliases.append(alias)

        display_name = aliases[0] if aliases else pad_alias
        label = " / ".join(aliases[:4]) if aliases else bank["raw_name"].replace("BP_", "")

        detail_lines = [
            f"Pad 名称: {pad_alias}",
            f"GPIO 索引: {gpio_index}",
            f"电源域: {iomux['domain'] or '-'}",
            f"默认复用: {default_function or pad_alias}",
            f"默认 IO 状态: {iomux['default_io_state'] or '-'}",
            f"IOMUX 复位值: {iomux['iomux_reset'] or '-'}",
        ]
        if iomux["override_0"]:
            detail_lines.append(f"Override 0: {iomux['override_0']}")
        if iomux["override_1"]:
            detail_lines.append(f"Override 1: {iomux['override_1']}")
        if len(iomux["functions"]) > 1:
            detail_lines.append("其它复用: " + ", ".join(iomux["functions"][1:]))

        pins.append(
            {
                "pin_number": pin_number,
                "pin_ref": pad_alias,
                "pin_index_label": str(gpio_index),
                "gpio_index": gpio_index,
                "label": label,
                "display_name": display_name,
                "aliases": aliases,
                "modules": classify_aliases(aliases),
                "primary_module": primary_module(aliases),
                "voltage_profile": {
                    "supports_1_8v": None,
                    "supports_3_3v": None,
                    "supports_1_8v_input_only": False,
                    "supports_5v_tolerant": False,
                    "summary": "当前 PPR 页未直接给出该 Pad 的 1.8V / 3.3V 电压容限。",
                    "notes": [
                        "当前解析页主要提供 IOMUX 复用、GPIO 索引、寄存器复位值和默认上下拉状态。",
                        "这些页面没有直接给出逐 Pad 的 1.8V / 3.3V 容限表。",
                    ],
                },
                "gpio_alt_info": None,
                "generic_info_rows": [
                    ("Pad 名称", pad_alias),
                    ("GPIO 索引", str(gpio_index)),
                    ("寄存器", bank["register"]),
                    ("复位值", bank["reset_value"]),
                    ("Bank", str(bank["bank"])),
                    ("电源域", iomux["domain"] or "-"),
                    ("默认功能", default_function or pad_alias),
                    ("默认 IO 状态", iomux["default_io_state"] or "-"),
                    ("IOMUX 复位值", iomux["iomux_reset"] or "-"),
                    ("复用功能 1", iomux["functions"][1] if len(iomux["functions"]) > 1 else "-"),
                    ("复用功能 2", iomux["functions"][2] if len(iomux["functions"]) > 2 else "-"),
                    ("复用功能 3", iomux["functions"][3] if len(iomux["functions"]) > 3 else "-"),
                ],
                "detail_entries": [
                    {
                        "page": iomux["page"],
                        "table": "Table 153",
                        "table_cn": "表 153",
                        "interface": "IOMUX Function Table",
                        "interface_cn": "IOMUX 功能表",
                        "signal_text": label,
                        "summary": default_function or pad_alias,
                        "summary_cn": f"默认功能: {default_function or pad_alias}",
                        "description": " | ".join(detail_lines),
                        "description_cn": "；".join(detail_lines),
                    },
                    {
                        "page": bank["page"],
                        "table": f"Table {bank['table_number']}",
                        "table_cn": f"表 {bank['table_number']}",
                        "interface": "GPIO Bank Register Table",
                        "interface_cn": "GPIO Bank 寄存器表",
                        "signal_text": bank["raw_name"],
                        "summary": bank["register"],
                        "summary_cn": f"寄存器: {bank['register']}",
                        "description": f"Reset={bank['reset_value']} | Source={bank['raw_name']}",
                        "description_cn": f"复位值={bank['reset_value']}；来源={bank['raw_name']}",
                    },
                ],
            }
        )

    _assign_functional_package_sides(pins)
    modules = build_module_index(pins)
    signals = build_signal_index(pins)

    return {
        "chip_id": "amd_family_19h_model_78h",
        "vendor": "AMD",
        "model": "Family 19h Model 78h A0",
        "display_name": "AMD Family 19h Model 78h",
        "category": "CPU / SoC",
        "family": "AMD Family 19h",
        "series": "Model 78h",
        "chip_role": "APU / Mobile Processor",
        "variants": ["FP7", "FP7r2"],
        "package": "功能封装视图",
        "package_type": "uBGA / Functional View",
        "view_type": "functional_package",
        "document_type": "PPR",
        "description": "AMD 移动处理器平台信号封装视图，当前已入库 IOMUX、GPIO Bank、常用控制与板级接口信息。",
        "features": [
            "支持按模块、信号、Pad 别名检索",
            "显示 IOMUX 复用、GPIO 索引、寄存器与默认状态",
            "适合作为板级调试时的功能封装参考",
        ],
        "pin_count": len(pins),
        "source_pdf": str(pdf_path),
        "source_pdf_name": pdf_path.name,
        "sections": extract_top_sections(pdf_path),
        "modules": modules,
        "signals": signals,
        "pins": pins,
        "notes": [
            "基于表 153（IOMUX Function Table）和表 155-157（GPIO Bank 表）生成。",
            "这份 PPR 在表 12 中明确给出的是 FP7 和 FP7r2 笔记本封装。",
            "第 120 页的 CPUID 包类型枚举里出现了 FP8，但文档没有给出完整的 FP8 球位图。",
            "当前程序里的封装图是外部可见 Pad 的功能封装视图，不是厂商机械 BGA 坐标图。",
            f"当前模块覆盖重点：{', '.join(top_module_names(modules))}。",
        ],
    }


def extract_top_sections(pdf_path: Path) -> list[dict]:
    doc = fitz.open(pdf_path)
    try:
        sections = []
        for level, title, page, *_rest in doc.get_toc(simple=False):
            if level == 1:
                sections.append({"title": title.strip(), "page": page})
        return sections
    finally:
        doc.close()


def build_it5570_chip(pdf_path: Path) -> dict:
    pins = parse_it5570_top_view(pdf_path)
    pin_detail_rows = parse_pin_descriptions(pdf_path)
    pin_detail_map = _build_pin_detail_map(pin_detail_rows)
    gpio_alt_map = parse_gpio_alt_functions(pdf_path)

    for pin in pins:
        detail_entries = pin_detail_map.get(pin["pin_number"], [])
        gpio_alt_info = gpio_alt_map.get(pin["pin_number"])
        voltage_profile = _voltage_profile(pin, detail_entries, gpio_alt_info)
        pin["detail_entries"] = detail_entries
        pin["gpio_alt_info"] = gpio_alt_info
        pin["voltage_profile"] = voltage_profile
        pin["supports_1_8v"] = voltage_profile["supports_1_8v"]
        pin["supports_3_3v"] = voltage_profile["supports_3_3v"]
        pin["supports_1_8v_input_only"] = voltage_profile["supports_1_8v_input_only"]
        pin["supports_5v_tolerant"] = voltage_profile["supports_5v_tolerant"]

    modules = build_module_index(pins)
    signals = build_signal_index(pins)

    return {
        "chip_id": "it5570_c",
        "vendor": "ITE",
        "model": "IT5570 C Version",
        "display_name": "IT5570E / IT5570VG",
        "category": "EC / Super I/O",
        "family": "IT5570",
        "series": "IT55xx",
        "chip_role": "Embedded Controller",
        "variants": ["IT5570E-128", "IT5570VG-128", "IT5570E-256", "IT5570VG-256"],
        "package": "LQFP-128L",
        "package_type": "LQFP",
        "view_type": "package_top",
        "document_type": "Datasheet",
        "description": "ITE EC / SIO 芯片封装库，包含引脚复用、电压能力、GPIO 电气属性和章节来源。",
        "features": [
            "支持查看 GPIO、eSPI、LPC、SMBus、PWM 等接口",
            "支持显示 1.8V、3.3V、5V tolerant 等电气能力",
            "适合作为 EC 原理图调试和引脚核对的离线资料库",
        ],
        "pin_count": 128,
        "source_pdf": str(pdf_path),
        "source_pdf_name": pdf_path.name,
        "sections": extract_top_sections(pdf_path),
        "modules": modules,
        "signals": signals,
        "pins": pins,
        "notes": [
            "封装顶视图名称来自 PDF 的 Pin Configuration 页面。",
            "引脚说明详情来自第 5 章 Pin Descriptions 表格。",
            "GPIO 电压与复用数据来自表 7-10。",
            f"当前模块覆盖重点：{', '.join(top_module_names(modules))}。",
        ],
    }


MS8510_LPC_ESPI_ALIASES = {
    "KBRST",
    "SERIRQ",
    "ALERT",
    "LFRAME",
    "ECS",
    "LAD0",
    "LAD1",
    "LAD2",
    "LAD3",
    "EIO0",
    "EIO1",
    "EIO2",
    "EIO3",
    "LPCCLK",
    "ESCK",
    "ECSMI",
    "PLTRST",
    "PWUREQ",
    "LPCPD",
    "LPCRST",
    "ERST",
    "ECSCI",
    "CLKRUN",
}
MS8510_FSPI_ALIASES = {"FSCK", "FMISO", "FMOSI", "FSCE"}


def parse_ms8510_top_view(pdf_path: Path) -> list[dict]:
    doc = fitz.open(pdf_path)
    try:
        page = doc.load_page(MS8510_TOP_VIEW_PAGE - 1)
        words = page.get_text("words")
    finally:
        doc.close()

    labels = []
    for word in words:
        text = _normalize_text(word[4])
        if not _is_signal_label(text) or text.isdigit():
            continue
        x = (word[0] + word[2]) * 0.5
        y = (word[1] + word[3]) * 0.5
        labels.append((x, y, text))

    left_labels = sorted(
        [item for item in labels if item[0] < 150.0 and 235.0 < item[1] < 510.0],
        key=lambda item: item[1],
    )
    bottom_labels = sorted(
        [item for item in labels if 160.0 < item[0] < 430.0 and 540.0 < item[1] < 565.0],
        key=lambda item: item[0],
    )
    right_labels = sorted(
        [item for item in labels if item[0] > 455.0 and 235.0 < item[1] < 510.0],
        key=lambda item: item[1],
    )
    top_labels = sorted(
        [item for item in labels if 165.0 < item[0] < 430.0 and 165.0 < item[1] < 215.0],
        key=lambda item: item[0],
    )

    if not (len(left_labels) == len(bottom_labels) == len(right_labels) == len(top_labels) == 32):
        raise RuntimeError(
            "Failed to parse MS8510 top-view pin labels: "
            f"left={len(left_labels)} bottom={len(bottom_labels)} right={len(right_labels)} top={len(top_labels)}"
        )

    pins: list[dict] = []
    for index, (_, _, label) in enumerate(left_labels):
        pins.append(_pin_record(index + 1, "left", index, label))
    for index, (_, _, label) in enumerate(bottom_labels):
        pins.append(_pin_record(index + 33, "bottom", index, label))
    for index, (_, _, label) in enumerate(right_labels):
        pins.append(_pin_record(96 - index, "right", index, label))
    for index, (_, _, label) in enumerate(top_labels):
        pins.append(_pin_record(128 - index, "top", index, label))
    return sorted(pins, key=lambda pin: pin["pin_number"])


def _normalize_ms8510_line(text: str) -> str:
    normalized = _normalize_text(text)
    normalized = re.sub(r"\s*/\s*", "/", normalized)
    return normalized.rstrip("_")


def _is_ms8510_pin_number_line(text: str) -> bool:
    return bool(re.fullmatch(r"[0-9,\-\s]+", _normalize_text(text)))


def _is_ms8510_type_line(text: str) -> bool:
    return any(token in text for token in ("数字输入/输出", "数字输入", "数字输出", "电源", "地"))


def _is_ms8510_group_line(text: str) -> bool:
    return text.startswith("GPIO_") or text in {"复位", "系统电源和地"}


def parse_ms8510_pin_descriptions(pdf_path: Path) -> list[dict]:
    doc = fitz.open(pdf_path)
    try:
        line_items: list[dict] = []
        skip_tokens = (
            "Tel:",
            "Fax:",
            "Web:",
            "宏晶微电子科技股份有限公司",
            "数据手册",
            "文档密级",
            "文件编号",
            "版本/修订",
            "MacroSilicon Release For",
            "Internal Use Only",
            "2023年07月19日",
            "引脚名称",
            "引脚 #",
            "类型",
            "描述",
            "6. 引脚描述",
            "表6.1 引脚描述",
        )

        for page_no in MS8510_PIN_DESCRIPTION_PAGES:
            page = doc.load_page(page_no - 1)
            page_lines: list[dict] = []
            for raw_line in page.get_text("text").splitlines():
                text = _normalize_ms8510_line(raw_line)
                if not text:
                    continue
                if text.startswith("第") and "页" in text:
                    continue
                if any(token in text for token in skip_tokens):
                    continue
                if text.startswith("/") and page_lines:
                    page_lines[-1]["text"] = _normalize_ms8510_line(page_lines[-1]["text"] + text)
                    continue
                if _is_ms8510_pin_number_line(text) and page_lines and _is_ms8510_pin_number_line(page_lines[-1]["text"]):
                    page_lines[-1]["text"] = f"{page_lines[-1]['text']}{text}"
                    continue
                page_lines.append({"page": page_no, "text": text})
            line_items.extend(page_lines)

        rows: list[dict] = []
        current_group = ""
        index = 0
        while index < len(line_items):
            text = line_items[index]["text"]
            if _is_ms8510_group_line(text):
                current_group = text
                index += 1
                continue

            if not _is_signal_label(text):
                index += 1
                continue

            next_index = index + 1
            if next_index >= len(line_items) or not _is_ms8510_pin_number_line(line_items[next_index]["text"]):
                index += 1
                continue

            signal_text = text
            pin_parts = [line_items[next_index]["text"]]
            row_page = line_items[index]["page"]
            cursor = next_index + 1
            while cursor < len(line_items) and _is_ms8510_pin_number_line(line_items[cursor]["text"]):
                pin_parts.append(line_items[cursor]["text"])
                cursor += 1

            attribute = ""
            if cursor < len(line_items) and _is_ms8510_type_line(line_items[cursor]["text"]):
                attribute = line_items[cursor]["text"]
                cursor += 1

            description_lines: list[str] = []
            while cursor < len(line_items):
                next_text = line_items[cursor]["text"]
                if _is_ms8510_group_line(next_text):
                    break
                if _is_signal_label(next_text) and cursor + 1 < len(line_items) and _is_ms8510_pin_number_line(line_items[cursor + 1]["text"]):
                    break
                description_lines.append(next_text)
                cursor += 1

            pin_text = "".join(pin_parts)
            summary = description_lines[0] if description_lines else attribute
            rows.append(
                {
                    "page": row_page,
                    "table": "表6.1",
                    "table_cn": "表6.1",
                    "interface": current_group or "引脚描述",
                    "interface_cn": current_group or "引脚描述",
                    "pin_text": pin_text,
                    "pin_numbers": expand_pin_numbers(pin_text),
                    "signal_text": signal_text,
                    "signals": split_aliases(signal_text),
                    "attribute": attribute,
                    "attribute_description": attribute,
                    "summary": summary,
                    "summary_cn": summary,
                    "description": " ".join(description_lines),
                    "description_cn": " ".join(description_lines),
                    "description_lines": description_lines,
                    "description_lines_cn": description_lines,
                }
            )
            index = cursor

        return [row for row in rows if row["pin_numbers"]]
    finally:
        doc.close()


def _ms8510_generic_info_rows(pin: dict, detail_entries: list[dict]) -> list[tuple[str, str]]:
    if not detail_entries:
        return []
    detail = detail_entries[0]
    rows: list[tuple[str, str]] = []
    if detail.get("interface_cn"):
        rows.append(("引脚分组", detail["interface_cn"]))
    if detail.get("attribute"):
        rows.append(("类型", detail["attribute"]))
    for line in detail.get("description_lines_cn", []):
        if "：" not in line:
            continue
        title, value = line.split("：", 1)
        rows.append((title, value))
    return rows


def _ms8510_voltage_profile(pin: dict, detail_entries: list[dict]) -> dict:
    aliases = set(pin.get("aliases", []))
    label = pin.get("display_name", "")
    detail_text = " ".join(detail.get("description_cn", "") for detail in detail_entries)

    if label == "NC" or any(alias.startswith("DVSS") for alias in aliases) or "AVSS" in aliases:
        return _operating_voltage_profile("地脚或空脚，不适用 1.8V / 3.3V 判定。")

    supports_1_8v = False
    supports_3_3v = False
    notes: list[str] = []

    if aliases & {"VCC", "VCC_FSPI"} or "3.3V/1.8V" in detail_text or aliases & MS8510_LPC_ESPI_ALIASES or aliases & MS8510_FSPI_ALIASES:
        supports_1_8v = True
        supports_3_3v = True
        notes.append("规格书对该接口或供电脚给出了 1.8V / 3.3V 双电压说明。")
    elif any(alias.startswith("DVDD33") for alias in aliases) or "AVDD33" in aliases:
        supports_3_3v = True
        notes.append("规格书明确标注为 3.3V 电源域。")
    elif any(token in detail_text for token in ("数字输入", "数字输入/输出", "数字输出", "电源")):
        supports_3_3v = True
        notes.append("当前引脚在手册中归类为 3.3V 数字/电源相关引脚。")

    if supports_1_8v and supports_3_3v:
        summary = "支持 1.8V / 3.3V 双电压接口。"
    elif supports_3_3v:
        summary = "默认按 3.3V 域使用。"
    else:
        summary = "手册未给出明确的 1.8V / 3.3V 切换说明。"

    return _operating_voltage_profile(summary, supports_1_8v=supports_1_8v, supports_3_3v=supports_3_3v, notes=notes)


def build_ms8510_chip(pdf_path: Path) -> dict:
    pins = parse_ms8510_top_view(pdf_path)
    pin_detail_rows = parse_ms8510_pin_descriptions(pdf_path)
    pin_detail_map = _build_pin_detail_map(pin_detail_rows)

    for pin in pins:
        detail_entries = pin_detail_map.get(pin["pin_number"], [])
        voltage_profile = _ms8510_voltage_profile(pin, detail_entries)
        pin["detail_entries"] = detail_entries
        pin["gpio_alt_info"] = None
        pin["generic_info_rows"] = _ms8510_generic_info_rows(pin, detail_entries)
        pin["voltage_profile"] = voltage_profile
        pin["supports_1_8v"] = voltage_profile["supports_1_8v"]
        pin["supports_3_3v"] = voltage_profile["supports_3_3v"]
        pin["supports_1_8v_input_only"] = voltage_profile["supports_1_8v_input_only"]
        pin["supports_5v_tolerant"] = voltage_profile["supports_5v_tolerant"]

    modules = build_module_index(pins)
    signals = build_signal_index(pins)
    return {
        "chip_id": "ms8510",
        "vendor": "MacroSilicon",
        "model": "MS8510",
        "display_name": "MS8510",
        "type_label": "EC芯片",
        "category": "Embedded Controller",
        "family": "MS85xx",
        "series": "MS8510",
        "chip_role": "Embedded Controller",
        "variants": ["MS8510"],
        "package": "LQFP-128",
        "package_type": "LQFP",
        "view_type": "package_top",
        "document_type": "Datasheet",
        "description": "MS8510 EC 芯片封装图，包含 128 引脚定义、中文引脚描述和接口复用信息。",
        "features": [
            "支持按模块、信号和引脚筛选 MS8510 的 128 个封装引脚",
            "引脚详情直接显示中文默认功能、复用功能和接口分组",
            "对 LPC/eSPI、FSPI 及相关供电脚给出 1.8V / 3.3V 双电压提示",
        ],
        "pin_count": len(pins),
        "source_pdf": str(pdf_path),
        "source_pdf_name": pdf_path.name,
        "sections": _sections_or_manual(
            pdf_path,
            [
                ("1. 基本介绍", 2),
                ("4. 功能框图", 12),
                ("5. 引脚图", 13),
                ("6. 引脚描述", 14),
                ("7. 时钟和复位", 21),
            ],
        ),
        "modules": modules,
        "signals": signals,
        "pins": pins,
        "notes": [
            "封装图直接取自第 13 页顶视图，并按真实四边顺序恢复到程序画布。",
            "引脚说明来自第 14-20 页《表 6.1 引脚描述》。",
            "当前版本优先沉淀引脚与接口复用信息，后续可继续扩展寄存器与功能块库。",
            f"当前模块覆盖重点：{', '.join(top_module_names(modules))}。",
        ],
    }


BQ25720_PIN_ORDER = [
    "VBUS",
    "ACN",
    "ACP",
    "CHRG_OK",
    "OTG/VAP/FRS",
    "ILIM_HIZ",
    "VDDA",
    "IADPT",
    "IBAT",
    "PSYS",
    "PROCHOT",
    "SDA",
    "SCL",
    "CMPIN",
    "CMPOUT",
    "COMP1",
    "COMP2",
    "CELL_BATPRESZ",
    "SRN",
    "SRP",
    "BATDRV",
    "VSYS",
    "SW2",
    "HIDRV2",
    "BTST2",
    "LODRV2",
    "PGND",
    "REGN",
    "LODRV1",
    "BTST1",
    "HIDRV1",
    "SW1",
]
BQ25720_PIN_SUMMARIES_CN = {
    "VBUS": "适配器输入电压引脚。",
    "ACN": "适配器电流检测负端输入。",
    "ACP": "适配器电流检测正端输入。",
    "CHRG_OK": "开漏电源良好指示输出。",
    "OTG/VAP/FRS": "OTG、VAP 和 FRS 模式使能输入。",
    "ILIM_HIZ": "输入电流限制与高阻模式控制引脚。",
    "VDDA": "内部参考偏置电源引脚。",
    "IADPT": "适配器电流监测输出，也用于电感参数配置。",
    "IBAT": "电池电流监测输出。",
    "PSYS": "系统功率监测输出。",
    "PROCHOT": "系统过载/限流告警输出。",
    "SDA": "SMBus 开漏数据输入输出。",
    "SCL": "SMBus 时钟输入。",
    "CMPIN": "独立比较器输入。",
    "CMPOUT": "独立比较器开漏输出。",
    "COMP1": "Buck-Boost 补偿网络引脚 1。",
    "COMP2": "Buck-Boost 补偿网络引脚 2。",
    "CELL_BATPRESZ": "电池节数设置与电池在位检测输入。",
    "SRN": "充电电流检测负端输入。",
    "SRP": "充电电流检测正端输入。",
    "BATDRV": "电池 FET 栅极驱动输出。",
    "VSYS": "系统电压检测输入。",
    "SW2": "Boost 功率级开关节点。",
    "HIDRV2": "Boost 高边 MOS 驱动输出。",
    "BTST2": "Boost 高边 MOS 自举电源。",
    "LODRV2": "Boost 低边 MOS 驱动输出。",
    "PGND": "功率地。",
    "REGN": "6V LDO 驱动电源输出。",
    "LODRV1": "Buck 低边 MOS 驱动输出。",
    "BTST1": "Buck 高边 MOS 自举电源。",
    "HIDRV1": "Buck 高边 MOS 驱动输出。",
    "SW1": "Buck 功率级开关节点。",
}


def _small_pin_name(raw_name: str) -> str:
    compact = re.sub(r"[\s_]+", "", raw_name.upper())
    mapping = {
        "CHRGOK": "CHRG_OK",
        "OTGVAPFRS": "OTG/VAP/FRS",
        "CELLBATPRESZ": "CELL_BATPRESZ",
        "THERMALPAD": "THERMAL_PAD",
        "INTN": "INT_N",
        "ALERTTHERM2": "ALERT/THERM2",
    }
    return mapping.get(compact, raw_name.strip().replace(" ", ""))


def _table_cell_text(value: str | None) -> str:
    if value is None:
        return ""
    return _normalize_text(str(value).replace("\xa0", " ")).strip("_")


def parse_bq25720_pin_rows(pdf_path: Path) -> dict[int, dict]:
    doc = fitz.open(pdf_path)
    try:
        rows: dict[int, dict] = {}
        for page_no in range(5, 8):
            page = doc.load_page(page_no - 1)
            for table in page.find_tables(strategy="lines_strict").tables:
                for row in table.extract():
                    if len(row) < 4:
                        continue
                    raw_name = _table_cell_text(row[0])
                    raw_number = _table_cell_text(row[1])
                    io_type = _table_cell_text(row[2]).upper()
                    description = _normalize_text(_table_cell_text(row[3]))
                    name = _small_pin_name(raw_name)
                    if name in {"PIN", "NAME", "THERMAL_PAD"} or not raw_number.isdigit():
                        continue
                    rows[int(raw_number)] = {
                        "page": page_no,
                        "name": name,
                        "io_type": io_type,
                        "description": description,
                    }
        return rows
    finally:
        doc.close()


def _bq25720_voltage_profile(name: str) -> dict:
    if name == "PGND":
        return _operating_voltage_profile("功率地，不适用 1.8V / 3.3V 判定。")
    if name in {"ACN", "ACP", "VBUS"}:
        return _range_voltage_profile("0V ~ 26V", min_value=0.0, max_value=26.0, notes=["来自 8.3 Recommended Operating Conditions。"])
    if name in {"SRN", "SRP", "VSYS"}:
        return _range_voltage_profile("0V ~ 19.2V", min_value=0.0, max_value=19.2, notes=["来自 8.3 Recommended Operating Conditions。"])
    if name in {"BTST1", "BTST2", "HIDRV1", "HIDRV2", "BATDRV"}:
        return _range_voltage_profile("0V ~ 32V", min_value=0.0, max_value=32.0, notes=["来自 8.3 Recommended Operating Conditions。"])
    if name in {"SW1", "SW2"}:
        return _range_voltage_profile("-2V ~ 26V", min_value=-2.0, max_value=26.0, notes=["来自 8.3 Recommended Operating Conditions。"])
    if name in {"SDA", "SCL", "REGN", "PSYS", "CHRG_OK", "CELL_BATPRESZ", "ILIM_HIZ", "LODRV1", "LODRV2", "VDDA", "COMP2", "CMPIN", "CMPOUT", "OTG/VAP/FRS"}:
        return _range_voltage_profile("0V ~ 6.5V", min_value=0.0, max_value=6.5, notes=["来自 8.3 Recommended Operating Conditions。"])
    if name == "PROCHOT":
        return _range_voltage_profile("0V ~ 5.3V", min_value=0.0, max_value=5.3, notes=["来自 8.3 Recommended Operating Conditions。"])
    if name in {"IADPT", "IBAT", "COMP1"}:
        return _range_voltage_profile("0V ~ 3.3V", min_value=0.0, max_value=3.3, notes=["来自 8.3 Recommended Operating Conditions。"])
    return _operating_voltage_profile("规格书未给出明确的 1.8V / 3.3V 判断，建议查看电气章节。")


def build_bq25720_chip(pdf_path: Path) -> dict:
    row_map = parse_bq25720_pin_rows(pdf_path)
    io_type_cn = {"PWR": "电源", "I": "输入", "O": "输出", "I/O": "输入/输出", "-": "-"}

    pins: list[dict] = []
    for pin_number, name in enumerate(BQ25720_PIN_ORDER, start=1):
        row = row_map[pin_number]
        pin = _base_pin_record(pin_number, name, f"P{pin_number:02d}")
        profile = _bq25720_voltage_profile(name)
        range_summary = profile["summary"].replace("引脚工作范围 ", "")
        summary_cn = BQ25720_PIN_SUMMARIES_CN.get(name, "功能摘要待补充。")
        pin["detail_entries"] = [
            _simple_detail_entry(
                page=row["page"],
                table="Table 7-1",
                table_cn="表 7-1",
                interface="Pin Functions",
                interface_cn="引脚功能",
                signal_text=name,
                summary=_first_sentence(row["description"]),
                summary_cn=summary_cn,
                description=row["description"],
                description_cn=f"{summary_cn} 工作范围：{range_summary}。",
                attribute=row["io_type"],
                attribute_description=io_type_cn.get(row["io_type"], row["io_type"]),
            )
        ]
        pin["gpio_alt_info"] = None
        pin["generic_info_rows"] = [
            ("引脚类型", io_type_cn.get(row["io_type"], row["io_type"])),
            ("封装脚位", f"P{pin_number:02d}"),
            ("工作范围", range_summary),
            ("功能摘要", summary_cn),
        ]
        pin["voltage_profile"] = profile
        pin["supports_1_8v"] = profile["supports_1_8v"]
        pin["supports_3_3v"] = profile["supports_3_3v"]
        pin["supports_1_8v_input_only"] = profile["supports_1_8v_input_only"]
        pin["supports_5v_tolerant"] = profile["supports_5v_tolerant"]
        pins.append(pin)

    _assign_standard_package_sides(pins, (8, 8, 8, 8))
    modules = build_module_index(pins)
    signals = build_signal_index(pins)
    return {
        "chip_id": "bq25720",
        "vendor": "Texas Instruments",
        "model": "BQ25720",
        "display_name": "TI BQ25720",
        "type_label": "充电IC",
        "category": "Battery Charger",
        "family": "BQ2572x",
        "series": "BQ25720",
        "chip_role": "Buck-Boost Charger",
        "variants": ["BQ25720"],
        "package": "WQFN-32",
        "package_type": "WQFN",
        "view_type": "functional_package",
        "document_type": "Datasheet",
        "description": "BQ25720 充电管理芯片功能封装图，包含 32 个引脚、中文功能摘要和主要电压范围。",
        "features": [
            "覆盖适配器检测、电池功率路径、SMBus 控制和 Buck-Boost 驱动引脚",
            "左侧详情直接显示引脚功能中文摘要和推荐工作范围",
            "适合做笔记本充电路径、限流与功率调试时的离线资料卡",
        ],
        "pin_count": len(pins),
        "source_pdf": str(pdf_path),
        "source_pdf_name": pdf_path.name,
        "sections": _sections_or_manual(
            pdf_path,
            [
                ("7 Pin Configuration and Functions", 5),
                ("8 Specifications", 8),
                ("9 Detailed Description", 24),
                ("10 Application and Implementation", 85),
            ],
        ),
        "modules": modules,
        "signals": signals,
        "pins": pins,
        "notes": [
            "当前封装图按 32-pin WQFN 标准逆时针编号恢复为功能视图。",
            "引脚功能来自第 5-7 页 Table 7-1 Pin Functions。",
            "电压范围来自第 8 页 Recommended Operating Conditions。",
            f"当前模块覆盖重点：{', '.join(top_module_names(modules))}。",
        ],
    }


CW2217_PIN_DEFS = [
    (1, "INT_N", "告警中断输出，开漏低有效。", "中断 / 状态"),
    (2, "NC", "空脚，不连接内部电路。", "NC"),
    (3, "VDD", "芯片电源输入。", "电源"),
    (4, "VCELL", "电池电压监测引脚。", "电池电压"),
    (5, "NC", "空脚，不连接内部电路。", "NC"),
    (6, "VSS", "地引脚。", "地"),
    (7, "CSP", "电流检测正端输入。", "电流检测"),
    (8, "CSN", "电流检测负端输入。", "电流检测"),
    (9, "TS", "NTC 温度检测输入。", "温度检测"),
    (10, "SDA", "I2C 数据输入输出。", "I2C"),
    (11, "SCL", "I2C 时钟输入。", "I2C"),
    (12, "NC", "空脚，不连接内部电路。", "NC"),
]


def _cw2217_voltage_profile(name: str) -> dict:
    if name in {"NC", "VSS"}:
        return _operating_voltage_profile("空脚或地脚，不适用 1.8V / 3.3V 判定。")
    if name == "VDD":
        return _range_voltage_profile("2.5V ~ 5.5V", min_value=2.5, max_value=5.5, notes=["来自 Recommended DC Operating Conditions。"])
    if name == "VCELL":
        return _range_voltage_profile("-0.3V ~ 5.0V", min_value=-0.3, max_value=5.0, notes=["来自 Recommended DC Operating Conditions。"])
    if name in {"CSP", "CSN"}:
        return _operating_voltage_profile("输入范围 -0.3V ~ VCELL+0.3V，随电池侧电压变化。", supports_1_8v=None, supports_3_3v=None)
    if name in {"INT_N", "TS", "SDA", "SCL"}:
        return _range_voltage_profile("-0.3V ~ 5.5V", min_value=-0.3, max_value=5.5, notes=["来自 Recommended DC Operating Conditions。"])
    return _operating_voltage_profile("规格书未给出明确的 1.8V / 3.3V 判断。")


def build_cw2217_chip(pdf_path: Path) -> dict:
    pins: list[dict] = []
    for pin_number, name, summary_cn, function_cn in CW2217_PIN_DEFS:
        pin = _base_pin_record(pin_number, name, f"P{pin_number}")
        profile = _cw2217_voltage_profile(name)
        pin["detail_entries"] = [
            _simple_detail_entry(
                page=3,
                table="Pin Descriptions",
                table_cn="引脚描述",
                interface="DFN-12 Top View",
                interface_cn="DFN-12 顶视图",
                signal_text=name,
                summary=summary_cn,
                summary_cn=summary_cn,
                description=summary_cn,
                description_cn=summary_cn,
            )
        ]
        pin["gpio_alt_info"] = None
        pin["generic_info_rows"] = [
            ("封装脚位", f"P{pin_number}"),
            ("功能分类", function_cn),
            ("工作范围", profile["summary"].replace("引脚工作范围 ", "")),
            ("功能摘要", summary_cn),
        ]
        pin["voltage_profile"] = profile
        pin["supports_1_8v"] = profile["supports_1_8v"]
        pin["supports_3_3v"] = profile["supports_3_3v"]
        pin["supports_1_8v_input_only"] = profile["supports_1_8v_input_only"]
        pin["supports_5v_tolerant"] = profile["supports_5v_tolerant"]
        pins.append(pin)

    _assign_standard_package_sides(pins, (6, 0, 6, 0))
    modules = build_module_index(pins)
    signals = build_signal_index(pins)
    return {
        "chip_id": "cw2217baad",
        "vendor": "Cellwise",
        "model": "CW2217BAAD",
        "display_name": "Cellwise CW2217BAAD",
        "type_label": "电量计",
        "category": "Fuel Gauge",
        "family": "CW22xx",
        "series": "CW2217",
        "chip_role": "Battery Fuel Gauge",
        "variants": ["CW2217BAAD"],
        "package": "DFN-12",
        "package_type": "DFN",
        "view_type": "package_top",
        "document_type": "Datasheet",
        "description": "CW2217BAAD 电量计封装图，包含 DFN-12 引脚分布、电池检测与 I2C 接口说明。",
        "features": [
            "支持查看 DFN-12 引脚分布和电量计测量链路",
            "详情面板显示电压、电流、温度和 I2C 相关脚位信息",
            "适合做电池包、电量计和 PMU 接线检查",
        ],
        "pin_count": len(pins),
        "source_pdf": str(pdf_path),
        "source_pdf_name": pdf_path.name,
        "sections": _sections_or_manual(
            pdf_path,
            [
                ("Typical Application", 2),
                ("Pin Configuration", 3),
                ("Absolute Maximum Ratings", 4),
                ("Electrical Characteristics", 5),
                ("Function Block Diagram", 7),
            ],
        ),
        "modules": modules,
        "signals": signals,
        "pins": pins,
        "notes": [
            "封装图根据第 3 页 DFN-12 Top View 重建。",
            "当前展示重点是电池电压、电流、温度和 I2C 接口脚位。",
            f"当前模块覆盖重点：{', '.join(top_module_names(modules))}。",
        ],
    }


CT7432_PIN_DEFS = [
    (1, "VCC", "芯片电源输入。", "电源"),
    (2, "DP1", "远端通道 1 正输入，可接二极管或三极管结。", "远端测温"),
    (3, "DN1", "远端通道 1 负输入，可接二极管或三极管结。", "远端测温"),
    (4, "DP2", "远端通道 2 正输入，可接二极管或三极管结。", "远端测温"),
    (5, "DN2", "远端通道 2 负输入，可接二极管或三极管结。", "远端测温"),
    (6, "GND", "地引脚。", "地"),
    (7, "THERM", "过温输出，开漏低有效，也用于 CT7432A 地址电阻选择。", "告警输出"),
    (8, "ALERT/THERM2", "告警输出，开漏低有效，可配置为第二路 THERM。", "告警输出"),
    (9, "SDA", "SMBus/I2C 数据输入输出。", "SMBus / I2C"),
    (10, "SCL", "SMBus/I2C 时钟输入。", "SMBus / I2C"),
]


def _ct7432_voltage_profile(name: str) -> dict:
    if name == "GND":
        return _operating_voltage_profile("地脚，不适用 1.8V / 3.3V 判定。")
    if name == "VCC":
        return _range_voltage_profile("2.7V ~ 5.5V", min_value=2.7, max_value=5.5, notes=["来自 Recommended Operating Conditions。"])
    if name in {"DP1", "DP2"}:
        return _operating_voltage_profile("输入范围 -0.3V ~ VCC+0.3V，随供电变化。", supports_1_8v=None, supports_3_3v=None)
    if name in {"DN1", "DN2"}:
        return _range_voltage_profile("-0.3V ~ 0.6V", min_value=-0.3, max_value=0.6, notes=["来自 Absolute Maximum Ratings。"])
    if name in {"THERM", "ALERT/THERM2", "SDA", "SCL"}:
        return _range_voltage_profile("-0.3V ~ 5.5V", min_value=-0.3, max_value=5.5, notes=["来自 Absolute Maximum Ratings。"])
    return _operating_voltage_profile("规格书未给出明确的 1.8V / 3.3V 判断。")


def build_ct7432_chip(pdf_path: Path) -> dict:
    pins: list[dict] = []
    for pin_number, name, summary_cn, function_cn in CT7432_PIN_DEFS:
        pin = _base_pin_record(pin_number, name, f"P{pin_number}")
        profile = _ct7432_voltage_profile(name)
        pin["detail_entries"] = [
            _simple_detail_entry(
                page=5,
                table="Pin Description",
                table_cn="引脚描述",
                interface="Sensor Pinout",
                interface_cn="温度传感器引脚定义",
                signal_text=name,
                summary=summary_cn,
                summary_cn=summary_cn,
                description=summary_cn,
                description_cn=summary_cn,
            )
        ]
        pin["gpio_alt_info"] = None
        pin["generic_info_rows"] = [
            ("封装脚位", f"P{pin_number}"),
            ("功能分类", function_cn),
            ("工作范围", profile["summary"].replace("引脚工作范围 ", "")),
            ("功能摘要", summary_cn),
        ]
        pin["voltage_profile"] = profile
        pin["supports_1_8v"] = profile["supports_1_8v"]
        pin["supports_3_3v"] = profile["supports_3_3v"]
        pin["supports_1_8v_input_only"] = profile["supports_1_8v_input_only"]
        pin["supports_5v_tolerant"] = profile["supports_5v_tolerant"]
        pins.append(pin)

    _assign_standard_package_sides(pins, (5, 0, 5, 0))
    modules = build_module_index(pins)
    signals = build_signal_index(pins)
    return {
        "chip_id": "ct7432",
        "vendor": "Sensylink",
        "model": "CT7432",
        "display_name": "Sensylink CT7432",
        "type_label": "温感",
        "category": "Temperature Sensor",
        "family": "CT74xx",
        "series": "CT7432",
        "chip_role": "Digital Temperature Sensor",
        "variants": ["CT7432", "CT7432A"],
        "package": "MSOP-10 / DFN3x3-10",
        "package_type": "MSOP / DFN",
        "view_type": "functional_package",
        "document_type": "Datasheet",
        "description": "CT7432 三通道数字温度传感器功能封装图，覆盖远端测温、ALERT 和 THERM 输出。",
        "features": [
            "支持查看 VCC、DP/DN、SMBus 和告警输出脚位",
            "详情面板显示 THERM、ALERT/THERM2 与远端测温输入的中文说明",
            "适合做 CPU / GPU / SoC 温感链路与过温保护信号核对",
        ],
        "pin_count": len(pins),
        "source_pdf": str(pdf_path),
        "source_pdf_name": pdf_path.name,
        "sections": _sections_or_manual(
            pdf_path,
            [
                ("Description", 4),
                ("Pin Description", 5),
                ("Absolute Maximum Ratings", 8),
                ("Register Map", 17),
                ("ALERT Output", 29),
                ("THERM Output", 33),
            ],
        ),
        "modules": modules,
        "signals": signals,
        "pins": pins,
        "notes": [
            "MSOP-10 与 DFN3x3-10 版本共用同一组引脚定义，当前按双列功能封装展示。",
            "第 5 页 Pin Description 中 pin7 为 THERM，pin8 为 ALERT/THERM2。",
            f"当前模块覆盖重点：{', '.join(top_module_names(modules))}。",
        ],
    }


def parse_asm1061_sections(pdf_path: Path) -> list[dict]:
    doc = fitz.open(pdf_path)
    try:
        page = doc.load_page(ASM1061_CONTENTS_PAGE - 1)
        sections: list[dict] = []
        pattern = re.compile(r"^(\d+)\.\s+(.+?)\s+(\d+)$")
        for raw_line in page.get_text("text").splitlines():
            line = _normalize_text(raw_line)
            match = pattern.match(line)
            if not match:
                continue
            index_text, title, page_text = match.groups()
            sections.append({"title": f"{index_text}. {title}", "page": int(page_text)})
        return sections
    finally:
        doc.close()


ASM1061_PROGRAMMING_ITEMS = [
    {
        "page": 4,
        "title": "设置 SATA Controller Subclass",
        "summary": "通过 PCI RXEC[2] 打开只读寄存器写权限，修改 RX0A 以切换 IDE / AHCI / RAID 子类码，完成后再关闭写权限。",
        "registers": ["RXEC[2]", "RX0A", "RX09", "RX0B"],
        "recommended": ["AHCI: RX0A=06h", "IDE: RX0A=01h", "RAID: RX0A=04h"],
    },
    {
        "page": 5,
        "title": "设置 Subsystem Vendor ID / Device ID",
        "summary": "同样通过 RXEC[2] 使能写入，然后把 RX2C~RX2F 改成客户自定义的 SVID / SSID。",
        "registers": ["RXEC[2]", "RX2C~RX2F"],
        "recommended": ["默认 SVID=1B21h", "默认 SSID=1060h"],
    },
    {
        "page": 6,
        "title": "SATA PHY 兼容性优化",
        "summary": "在设备 Spin-Up 之前，为 Port 0 / Port 1 分别写入 PHY 参数，改善 SATA 设备兼容性。",
        "registers": ["RXCA4", "RXCA5", "RXCAE", "RXDA4", "RXDA5", "RXDAE"],
        "recommended": ["RXCA4=ABh", "RXCA5=26h", "RXCAE=92h", "RXDA4=ABh", "RXDA5=26h", "RXDAE=92h"],
    },
    {
        "page": 7,
        "title": "Spin-Up SATA Device",
        "summary": "通过 RXEC[1:0] 控制两个 SATA 端口 Spin-Up。IDE 模式必须设置，AHCI 模式建议设置。",
        "registers": ["RXEC[1:0]"],
        "recommended": ["RXEC[1:0]=11b"],
    },
    {
        "page": 7,
        "title": "内部稳压器设置",
        "summary": "若 ASM1061 使用内部 regulator，建议在 Spin-Up 前把 PWM 参考电压调到 1.28V。使用外部 regulator 时写该值无副作用。",
        "registers": ["RXA12[4:3]"],
        "recommended": ["RXA12[4:3]=11b"],
    },
    {
        "page": 8,
        "title": "Feature Registers 推荐值",
        "summary": "推荐配置 RxFD / RxFE / RxFF 以改善系统兼容性、S4 唤醒、ATA/ATAPI 和 HDD 行为。",
        "registers": ["RXFD", "RXFE", "RXFF"],
        "recommended": ["RXFD[0]=1", "RXFE[5:4]=11b", "RXFE[1:0]=11b when L1 enabled", "RXFF[7]=1"],
    },
    {
        "page": 9,
        "title": "PCIe L0s / L1 电源管理兼容性",
        "summary": "为兼容性，L0s 与 L1 active state 默认建议关闭。若启用 L1，则 RXFE[1:0] 必须同时设为 11b。",
        "registers": ["RXA01[1:0]", "RXFE[1:0]"],
        "recommended": ["RXA01[0]=0", "RXA01[1]=0", "如果 L1 enable，则 RXFE[1:0]=11b"],
    },
    {
        "page": 10,
        "title": "AHCI 模式下关闭 eSATA / Hot-Plug",
        "summary": "为避免 Windows 把 HDD 显示在可安全移除列表中，需要把 HBA CAP.SXS 与两个端口的 PxCMD.HPCP 映射位清零。",
        "registers": ["RXE5C[5]", "RXFF[0]", "RXFF[1]"],
        "recommended": ["RXE5C[5]=0", "RXFF[0]=1", "RXFF[1]=1"],
    },
    {
        "page": 11,
        "title": "SSC 控制",
        "summary": "为了降低 EMI，推荐启用 SSC。先设置模式，再延时至少 100ns，最后拉起 enable bit。",
        "registers": ["RXA10[4:2]", "RXA10[0]"],
        "recommended": ["RXA10[4:2]=011b", "delay >= 100ns", "RXA10[0]=1"],
    },
    {
        "page": 12,
        "title": "PCIe Max Payload Size",
        "summary": "ASM1061 的 Device Control Register 默认是 128 bytes。不要设置成大于 256 bytes，否则与 Root Port 的传输会出错。",
        "registers": ["RX88[7:5]"],
        "recommended": ["RX88[7:5]=000b or 001b"],
    },
    {
        "page": 13,
        "title": "System BIOS 编程时机",
        "summary": "所有关键寄存器应在 Cold Boot、Warm Boot、S3 Resume、S4 Resume，且在分配 PCI 资源之前完成。",
        "registers": [],
        "recommended": ["Before assigning PCI resources"],
    },
    {
        "page": 13,
        "title": "Shadow RAM Cacheable",
        "summary": "若系统使用 Legacy OPROM，应把 ASM1061 OPROM 占用的 shadow RAM 设为 cacheable，以避免 DOS / Ghost 场景性能明显下降。",
        "registers": [],
        "recommended": ["Set OPROM shadow RAM cacheable"],
    },
    {
        "page": 13,
        "title": "关闭 64-bit Addressing Capability",
        "summary": "若 AHCI 64-bit addressing 存在兼容性问题，可清除 CAP.S64A，并把两个端口的 CLBU / FBU Upper 32-bit 清零。",
        "registers": ["RXE5F[7]", "AHCI MMIO 104h", "AHCI MMIO 10Ch", "AHCI MMIO 184h", "AHCI MMIO 18Ch"],
        "recommended": ["RXE5F[7]=0", "P0CLBU=0", "P0FBU=0", "P1CLBU=0", "P1FBU=0"],
    },
]


def build_asm1061_chip(pdf_path: Path) -> dict:
    sections = parse_asm1061_sections(pdf_path)
    return {
        "chip_id": "asm1061",
        "vendor": "ASMedia",
        "model": "ASM1061",
        "display_name": "ASMedia ASM1061",
        "category": "Storage Controller",
        "family": "ASM106x",
        "series": "ASM1061",
        "chip_role": "PCIe to SATA Host Controller",
        "variants": ["ASM1061"],
        "package": "文档资料卡",
        "package_type": "Unknown",
        "view_type": "document_only",
        "document_type": "Programming Note",
        "description": "ASM1061 是一颗 PCIe 转 SATA 控制器。这份资料不包含封装与引脚图，重点是 System BIOS 初始化顺序、关键寄存器和兼容性推荐值。",
        "features": [
            "支持 2 个 SATA 端口",
            "支持 BIOS 直接配置 PCI / AHCI 相关寄存器",
            "覆盖 SATA PHY、PCIe ASPM、SSC、AHCI CAP 与 64-bit Addressing 控制",
        ],
        "pin_count": 0,
        "source_pdf": str(pdf_path),
        "source_pdf_name": pdf_path.name,
        "sections": sections,
        "modules": [],
        "signals": [],
        "pins": [],
        "programming_items": ASM1061_PROGRAMMING_ITEMS,
        "notes": [
            "这是一份编程说明，不是 datasheet 或 pinout 手册。",
            "当前 PDF 未给出封装图、球位图、引脚定义或电气特性表。",
            "适合作为 BIOS 初始化与兼容性调优资料卡接入芯片库。",
            "目录中有 Legacy OPROM Backward Compatible 条目，但正文未提供独立寄存器配置细节。",
        ],
    }


def build_library() -> dict:
    chips = []
    if IT5570_PDF.exists():
        chips.append(build_it5570_chip(IT5570_PDF))
    if MS8510_PDF.exists():
        chips.append(build_ms8510_chip(MS8510_PDF))
    if IT8613_PDF.exists():
        chips.append(build_it8613_chip(IT8613_PDF))
    if IT8625_PDF.exists():
        chips.append(build_it8625_chip(IT8625_PDF))
    if IT8728_PDF.exists():
        chips.append(build_it8728_chip(IT8728_PDF))
    if IT8772_PDF.exists():
        chips.append(build_it8772_chip(IT8772_PDF))
    if IT8786_PDF.exists():
        chips.append(build_it8786_chip(IT8786_PDF))
    if ASM1061_PDF.exists():
        chips.append(build_asm1061_chip(ASM1061_PDF))
    if AMD_57396_PDF.exists():
        chips.append(build_amd_57396_chip(AMD_57396_PDF))
    if BQ25720_PDF.exists():
        chips.append(build_bq25720_chip(BQ25720_PDF))
    if CW2217_PDF.exists():
        chips.append(build_cw2217_chip(CW2217_PDF))
    if CT7432_PDF.exists():
        chips.append(build_ct7432_chip(CT7432_PDF))
    library = {
        "schema_version": LIBRARY_SCHEMA_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "root": str(ROOT_DIR),
        "chip_count": len(chips),
        "chips": chips,
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LIBRARY_PATH.write_text(json.dumps(library, ensure_ascii=False, indent=2), encoding="utf-8")
    return library


def ensure_library() -> dict:
    if not LIBRARY_PATH.exists():
        return build_library()
    try:
        library = json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return build_library()

    if library.get("schema_version") != LIBRARY_SCHEMA_VERSION:
        return build_library()

    chips = library.get("chips", [])
    if chips:
        first_pin = chips[0].get("pins", [{}])[0]
        if "voltage_profile" not in first_pin or "detail_entries" not in first_pin:
            return build_library()

    source_mtime = max(
        [
            pdf_path.stat().st_mtime
            for pdf_path in (
                IT5570_PDF,
                MS8510_PDF,
                IT8613_PDF,
                IT8625_PDF,
                IT8728_PDF,
                IT8772_PDF,
                IT8786_PDF,
                ASM1061_PDF,
                AMD_57396_PDF,
                BQ25720_PDF,
                CW2217_PDF,
                CT7432_PDF,
            )
            if pdf_path.exists()
        ],
        default=0.0,
    )
    library_mtime = LIBRARY_PATH.stat().st_mtime
    if source_mtime > library_mtime:
        return build_library()
    return library


if __name__ == "__main__":
    build_library()
