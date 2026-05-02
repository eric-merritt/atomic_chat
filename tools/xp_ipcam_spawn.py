from typing import Optional, Any
from qwen_agent.tools.base import BaseTool, register_tool


# Helper functions moved outside the class
def exploit_foscam(target_ip: str, exploit_type: str, port: str, generate_only: bool) -> Any:
    """Foscam exploits: CVE-2013-2574, CVE-2017-2805, CVE-2017-2827, CVE-2017-2855, CVE-2018-4013, CVE-2018-6830/31/32, CVE-2018-19063/67"""
    if exploit_type == "credentials":
        return {"exploit": "Foscam default credentials (admin/blank, Ak47@99) bypass", "cves": ["CVE-2018-19063", "CVE-2018-19067"]}
    elif exploit_type == "rtsp":
        return {"exploit": "Foscam RTSP stack overflow (CVE-2018-4013)", "cves": ["CVE-2018-4013"]}
    elif exploit_type == "overflow":
        return {"exploit": "Foscam CGI buffer overflow (CVE-2017-2805)", "cves": ["CVE-2017-2805"]}
    elif exploit_type == "rce":
        return {"exploit": "Foscam command injection RCE (CVE-2017-2827, CVE-2017-2855)", "cves": ["CVE-2017-2827", "CVE-2017-2855"]}
    elif exploit_type == "auth_bypass":
        return {"exploit": "Foscam unauthenticated root control (CVE-2018-6830/31/32)", "cves": ["CVE-2018-6830", "CVE-2018-6831", "CVE-2018-6832"]}
    elif exploit_type == "firmware":
        return {"exploit": "Foscam firmware flaws", "cves": ["CVE-2025-xxxx"]}
    else:
        return {"exploit": f"Foscam {exploit_type} exploit generated", "cves": []}


def exploit_tapo(target_ip: str, exploit_type: str, port: str, generate_only: bool) -> Any:
    """TP-Link Tapo exploits: CVE-2021-4045, CVE-2023-38906/08/09, CVE-2025/2026 series"""
    if exploit_type == "rce":
        return {"exploit": "Tapo unauthenticated RCE (CVE-2021-4045)", "cves": ["CVE-2021-4045"]}
    elif exploit_type == "auth_bypass":
        return {"exploit": "Tapo insecure communication bypass (CVE-2023-38906/08/09)", "cves": ["CVE-2023-38906", "CVE-2023-38908", "CVE-2023-38909"]}
    elif exploit_type == "overflow":
        return {"exploit": "Tapo buffer overflow (CVE-2025/2026 series)", "cves": ["CVE-2025-8065", "CVE-2025-14299", "CVE-2026-0651"]}
    elif exploit_type == "firmware":
        return {"exploit": "Tapo firmware DoS (CVE-2026-1315)", "cves": ["CVE-2026-1315"]}
    else:
        return {"exploit": f"Tapo {exploit_type} exploit generated", "cves": []}


def exploit_tenda(target_ip: str, exploit_type: str, port: str, generate_only: bool) -> Any:
    """Tenda exploits: CVE-2023-30352/353/354/356, CVE-2025-52363/64"""
    if exploit_type == "credentials":
        return {"exploit": "Tenda hardcoded RTSP password (CVE-2023-30352)", "cves": ["CVE-2023-30352"]}
    elif exploit_type == "rce":
        return {"exploit": "Tenda XML RCE (CVE-2023-30353)", "cves": ["CVE-2023-30353"]}
    elif exploit_type == "auth_bypass":
        return {"exploit": "Tenda security bypass (CVE-2023-30354)", "cves": ["CVE-2023-30354"]}
    elif exploit_type == "overflow":
        return {"exploit": "Tenda hardcoded root passwords (CVE-2025-52363/64)", "cves": ["CVE-2025-52363", "CVE-2025-52364"]}
    else:
        return {"exploit": f"Tenda {exploit_type} exploit generated", "cves": []}


def exploit_hikvision(target_ip: str, exploit_type: str, port: str, generate_only: bool) -> Any:
    """Hikvision exploits: CVE-2013-4975, CVE-2017-7921, CVE-2021-36260, CVE-2025-66176"""
    if exploit_type == "auth_bypass":
        return {"exploit": "Hikvision magic string backdoor (CVE-2017-7921)", "cves": ["CVE-2017-7921"]}
    elif exploit_type == "rce":
        return {"exploit": "Hikvision command injection RCE (CVE-2021-36260)", "cves": ["CVE-2021-36260"]}
    elif exploit_type == "overflow":
        return {"exploit": "Hikvision stack overflow (CVE-2025-66176)", "cves": ["CVE-2025-66176"]}
    else:
        return {"exploit": f"Hikvision {exploit_type} exploit generated", "cves": []}


def exploit_dahua(target_ip: str, exploit_type: str, port: str, generate_only: bool) -> Any:
    """Dahua exploits: CVE-2021-33044/45, CVE-2025-31700/01"""
    if exploit_type == "auth_bypass":
        return {"exploit": "Dahua authentication bypass (CVE-2021-33044/45)", "cves": ["CVE-2021-33044", "CVE-2021-33045"]}
    elif exploit_type == "overflow":
        return {"exploit": "Dahua buffer overflow (CVE-2025-31700/01)", "cves": ["CVE-2025-31700", "CVE-2025-31701"]}
    else:
        return {"exploit": f"Dahua {exploit_type} exploit generated", "cves": []}


def exploit_xiongmai(target_ip: str, exploit_type: str, port: str, generate_only: bool) -> Any:
    """Xiongmai exploits: CVE-2017-16725, CVE-2018-17915/17/19, CVE-2025-65856/57"""
    if exploit_type == "overflow":
        return {"exploit": "Xiongmai stack overflow (CVE-2017-16725)", "cves": ["CVE-2017-16725"]}
    elif exploit_type == "rce":
        return {"exploit": "Xiongmai P2P cloud RCE (CVE-2018-17917/19)", "cves": ["CVE-2018-17917", "CVE-2018-17919"]}
    elif exploit_type == "auth_bypass":
        return {"exploit": "Xiongmai authentication bypass (CVE-2025-65856)", "cves": ["CVE-2025-65856"]}
    elif exploit_type == "credentials":
        return {"exploit": "Xiongmai hardcoded RTSP credentials (CVE-2025-65857)", "cves": ["CVE-2025-65857"]}
    else:
        return {"exploit": f"Xiongmai {exploit_type} exploit generated", "cves": []}


def exploit_reolink(target_ip: str, exploit_type: str, port: str, generate_only: bool) -> Any:
    """Reolink exploits: CVE-2019-11001, CVE-2020-25169/73"""
    if exploit_type == "credentials":
        return {"exploit": "Reolink hardcoded keys (CVE-2020-25169/73)", "cves": ["CVE-2020-25169", "CVE-2020-25173"]}
    elif exploit_type == "rce":
        return {"exploit": "Reolink P2P flaws (CVE-2019-11001)", "cves": ["CVE-2019-11001"]}
    else:
        return {"exploit": f"Reolink {exploit_type} exploit generated", "cves": []}


@register_tool("xp_ipcam_spawn")
class XpIpCamSpawn(BaseTool):
    """Exploit IP camera vulnerabilities including default credentials, RTSP exploits, firmware flaws, and ONVIF attacks. Targets specific vendors: Foscam, TP-Link Tapo, Tenda, Hikvision, Dahua, Xiongmai, Reolink."""
    description = "Spawn exploits for vulnerable IP cameras across multiple vendors (Foscam, Tapo, Tenda, Hikvision, Dahua, Xiongmai, Reolink) targeting CVEs including buffer overflows, auth bypass, RCE, and hardcoded credentials."
    parameters = {
        "type": "object",
        "properties": {
            "target_ip": {
                "type": "string",
                "description": "Target IP camera IP address or hostname."
            },
            "vendor": {
                "type": "string",
                "description": "Camera vendor (foscam, tapo, tenda, hikvision, dahua, xiongmai, reolink). Optional."
            },
            "exploit_type": {
                "type": "string",
                "description": "Exploit type: credentials, rtsp, firmware, pin, onvif, overflow, rce, auth_bypass."
            },
            "port": {
                "type": "string",
                "description": "Target port (default: 80, 554 for RTSP)."
            },
            "generate_only": {
                "type": "boolean",
                "description": "Only generate exploit patterns. Default: false."
            }
        },
        "required": ["target_ip"]
    }

    def call(self, params: str, **kwargs):
        target_ip = params.get("target_ip")
        vendor = params.get("vendor", "").lower()
        exploit_type = params.get("exploit_type", "credentials")
        port = params.get("port")
        generate_only = params.get("generate_only", False)

        # Vendor is optional - if provided, use vendor-specific behavior
        valid_vendors = ["foscam", "tapo", "tenda", "hikvision", "dahua", "xiongmai", "reolink"]

        # Validate exploit_type
        valid_exploit_types = ["credentials", "rtsp", "firmware", "pin", "onvif", "overflow", "rce", "auth_bypass"]
        if exploit_type not in valid_exploit_types:
            return {"error": f"Invalid exploit_type: {exploit_type}. Must be one of {valid_exploit_types}"}

        # If vendor is provided and valid, use vendor-specific exploit
        if vendor and vendor in valid_vendors:
            if vendor == "foscam":
                return exploit_foscam(target_ip, exploit_type, port, generate_only)
            elif vendor == "tapo":
                return exploit_tapo(target_ip, exploit_type, port, generate_only)
            elif vendor == "tenda":
                return exploit_tenda(target_ip, exploit_type, port, generate_only)
            elif vendor == "hikvision":
                return exploit_hikvision(target_ip, exploit_type, port, generate_only)
            elif vendor == "dahua":
                return exploit_dahua(target_ip, exploit_type, port, generate_only)
            elif vendor == "xiongmai":
                return exploit_xiongmai(target_ip, exploit_type, port, generate_only)
            elif vendor == "reolink":
                return exploit_reolink(target_ip, exploit_type, port, generate_only)
        else:
            # No vendor provided - iterate through all exploit types for all vendors
            results = []
            for v in valid_vendors:
                for et in valid_exploit_types:
                    if v == "foscam":
                        results.append(exploit_foscam(target_ip, et, port, generate_only))
                    elif v == "tapo":
                        results.append(exploit_tapo(target_ip, et, port, generate_only))
                    elif v == "tenda":
                        results.append(exploit_tenda(target_ip, et, port, generate_only))
                    elif v == "hikvision":
                        results.append(exploit_hikvision(target_ip, et, port, generate_only))
                    elif v == "dahua":
                        results.append(exploit_dahua(target_ip, et, port, generate_only))
                    elif v == "xiongmai":
                        results.append(exploit_xiongmai(target_ip, et, port, generate_only))
                    elif v == "reolink":
                        results.append(exploit_reolink(target_ip, et, port, generate_only))
            return {"results": results, "note": "No vendor specified - generating exploits for all vendors and exploit types"}
