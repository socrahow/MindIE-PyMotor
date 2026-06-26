import json
import argparse
import requests
import sys
from typing import List, Dict, Any
from dataclasses import dataclass

@dataclass
class NodeConfig:
    """
    节点配置信息
    """
    ip: str
    business_port_base: int = 1025
    mgmt_port_base: int = 9000
    node_count: int = 1 # 每个IP的节点数


@dataclass
class InstanceConfig:
    """
    实例配置
    """
    id: int
    role: str
    job_name: str
    model_name: str
    nodes: List[NodeConfig]


class InstanceGenerator:
    """
    实例配置生成器
    """

    # 默认IP映射关系
    IP_MAPPING = {
        '1': '80.48.37.141'
    }

    def __init__(self, prefill_list: str = "", decode_list: str = "", union_list: str = ""):
        self.prefill_ids = self._parse_id_list(prefill_list)
        self.decode_ids = self._parse_id_list(decode_list)
        self.union_ids = self._parse_id_list(union_list)

    def _parse_id_list(self, id_str: str) -> List[str]:
        """
        解析节点ID列表，支持逗号分隔或连续字符串
        """
        if not id_str:
            return []
        # 移除空格并按逗号分隔
        ids = id_str.replace(" ", "").split(",")
        # 如果没有逗号，将字符串拆分为单个字符
        if len(ids) == 1 and len(ids[0]) > 1:
            return list(ids[0])
        return ids

    def _generate_endpoints(self, node_ids: List[str], role: str) -> Dict[str, Any]:
        """
        为给定的节点ID列表生成endpoints配置
        """
        endpoints = {}
        global_id = 0 # 全局id计数器
        p_business_port = 30000
        d_business_port = 40000
        u_business_port = 50000
        port = p_business_port

        if role == "prefill": # prefill
            node_count = 1 # prefiller 每个IP 1个节点
        elif role == "decode": # decode
            node_count = 1 # decoder 每个IP 1个节点
            port = d_business_port
        else: # union
            node_count = 1 # unioner 每个IP 1个节点
            port = u_business_port
        
        for node_id in node_ids:
            if node_id not in self.IP_MAPPING:
                print(f"警告：节点ID '{node_id}' 没有对应的IP映射，已跳过")
                continue

            ip = self.IP_MAPPING[node_id]
            ip_endpoints = {}

            for i in range(node_count):
                ip_endpoints[str(global_id)] = {
                    "id": global_id,
                    "ip": ip,
                    "business_port": str(port + (global_id % node_count)), # 使用不同的端口
                    "mgmt_port": str(port + 1000 + (global_id % node_count))
                }
                global_id += 1
            endpoints[ip] = ip_endpoints
        return endpoints

    def generate_prefill_instance(self) -> Dict[str, Any]:
        """
        生成prefill实例
        """
        if not self.prefill_ids:
            return None
        return {
            "id": 0,
            "role": "prefill",
            "endpoints": self._generate_endpoints(self.prefill_ids, "prefill"),
            "job_name": "qwen3.5-0.8b",
            "model_name": "qwen"
        }

    def generate_decode_instance(self) -> Dict[str, Any]:
        """
        生成decode实例
        """
        if not self.decode_ids:
            return None
        return {
            "id": 1,
            "role": "decode",
            "endpoints": self._generate_endpoints(self.decode_ids, "decode"),
            "job_name": "qwen3.5-0.8b",
            "model_name": "qwen"
        }

    def generate_union_instance(self) -> Dict[str, Any]:
        """
        生成union实例
        """
        if not self.union_ids:
            return None
        return {
            "id": 0,
            "role": "union",
            "endpoints": self._generate_endpoints(self.union_ids, "union"),
            "job_name": "qwen3.5-0.8b",
            "model_name": "qwen"
        }

    def generate_request_json(self) -> Dict[str, Any]:
        """
        生成完整的请求JSON
        """
        instances = []

        prefill_instance = self.generate_prefill_instance()
        if prefill_instance:
            instances.append(prefill_instance)
        decode_instance = self.generate_decode_instance()
        if decode_instance:
            instances.append(decode_instance)
        union_instance = self.generate_union_instance()
        if union_instance:
            instances.append(union_instance)

        if not instances:
            raise ValueError("必须至少指定一个prefill、decode或union节点")
        return {
            "event": "add",
            "instances": instances
        }

    def print_help(self):
        """
        打印帮助信息
        """
        print("可用节点ID映射关系：")
        print("-" * 40)
        for node_id, ip in self.IP_MAPPING.items():
            print(f" {node_id} -> {ip}")
        print("\n使用示例：")
        print(" python refresh_instances.py --union-list 1")
        print(" python refresh_instances.py --prefill-list 123 --decode-list 45")
        print(" python refresh_instances.py --prefill-list 1,2,3 --decode-list 4,5")
        print(" python refresh_instances.py --prefill-list 1,2,3 --decode-list 4,5 --dry-run")
        print("\n这将：")
        print(" - PD混部：使用节点1")
        print(" - prefiller：使用节点1,2,3")
        print(" - decoder：使用节点4,5")
        print(" - 仅打印配置信息")

def send_request(json_data: Dict[str, Any], proxy_url:str = "http://127.0.0.1:1026/instances/refresh"):
    """
    发送请求到代理服务
    """
    headers = {
        "Content-Type": "application/json"
    }
    try:
        print(f"发送请求到：{proxy_url}")
        print("请求体：")
        print(json.dumps(json_data, indent=2, ensure_ascii=False))
        print("-" * 80)

        response =requests.post(
            proxy_url,
            headers=headers,
            json=json_data,
            timeout=30
        )
        print(f"响应状态码：{response.status_code}")
        if response.status_code == 200:
            print("请求成功！")
            try:
                resp_json = response.json()
                print("响应内容：")
                print(json.dumps(resp_json, indent=2, ensure_ascii=False))
            except:
                print(f"响应文本： {response.text}")
        else:
            print("请求失败！")
            print(f"错误信息： {response.text}")
        return response
    except requests.exceptions.RequestException as e:
        print(f"请求异常： {e}")
        return None

def main():
    parser = argparse.ArgumentParser(
        description="VLLM 负载均衡代理配置生成器"
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
        示例：
        %(prog)s --union-list 1
        %(prog)s --prefill-list 123 --decode-list 45
        %(prog)s --prefill-list 1,2,3 --decode-list 4,5
        %(prog)s --prefill-list 123 --decode-list 45 --dry-run
        %(prog)s --help-list
        %(prog)s --prefill-list 123 --decode-list 45 --url http://10.0.0.1:1026/instances/refresh
        """
    )
    parser.add_argument(
        "--prefill-list",
        type=str,
        default="",
        help="Prefiller节点ID列表，支持逗号分隔或连续字符串（如 123 或 1,2,3）"
    )
    parser.add_argument(
        "--decode-list",
        type=str,
        default="",
        help="Decoder节点ID列表，支持逗号分隔或连续字符串（如 123 或 1,2,3）"
    )
    parser.add_argument(
        "--union-list",
        type=str,
        default="",
        help="PD混部节点ID列表，支持逗号分隔或连续字符串（如 123 或 1,2,3）"
    )
    parser.add_argument(
        "--url",
        type=str,
        default="http://127.0.0.1:1026/instances/refresh",
        help="代理服务URL（默认：http://127.0.0.1:1026/instances/refresh）"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只生成JSON，不发送请求"
    )
    parser.add_argument(
        "--help-list",
        action="store_true",
        help="显示节点ID映射关系"
    )
    args = parser.parse_args()

    if args.help_list:
        generator = InstanceGenerator()
        generator.print_help()
        return
    # 检查参数
    if not args.prefill_list and not args.decode_list and not args.union_list:
        print("错误：必须至少指定 --prefill-list、--decode-list或--union-list")
        print("使用--help-list查看完整帮助")
    # 生成配置
    try:
        generator = InstanceGenerator(args.prefill_list, args.decode_list, args.union_list)
        request_json = generator.generate_request_json()
        print("=" * 80)
        print("生成的配置摘要：")
        print("=" * 80)
        instances = request_json.get("instances", [])
        for instance in instances:
            role = instance.get("role", "")
            endpoints = instance.get("endpoints", {})
            ip_count = len(endpoints)
            total_nodes = sum(len(nodes) for nodes in endpoints.values())
            print(f"\n{role.upper()} 实例：")
            print(f" - 包含 {ip_count} 个IP")
            print(f" - 共 {total_nodes} 个节点")
            for ip, nodes in endpoints.items():
                print(f"  - IP {ip}： {len(nodes)} 个节点")
                for node_id, node_info in nodes.items():
                    print(f"   节点{node_id}：业务端口 {node_info['business_port']}，管理端口 {node_info['mgmt_port']}")
        print("\n" + "=" * 80)
        if args.dry_run:
            print("完整JSON（dry-run模式，不发送）")
            print(json.dumps(request_json, indent=2, ensure_ascii=False))
        else:
            response = send_request(request_json, args.url)
            if response and response.status_code == 200:
                print("配置更新完成！")
            else:
                print("配置更新失败！")
                sys.exit(1)
    except ValueError as e:
        print(f"错误：{e}")
        sys.exit(1)
    except Exception as e:
        print(f"未预期错误：{e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__=="__main__":
    main()