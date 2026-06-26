# 单独部署Coordinator服务

## 场景介绍
该方案适用与没有安装k8s的场景，由coordinate进行请求分发。

## 部署方式
### 启动Coordinator服务
#### 1、编译安装代码仓
```
git clone https://github.com/socrahow/MindIE-PyMotor.git
cd MindIE-PyMotor
git checkout pdmix
pip install -r requirements.txt
bash build.sh
pip install -e .
```
#### 2、修改Coordinator配置文件
可以按照后端服务真是部署情况修改`user_config.json`文件
```
vim examples/infer_engines/vllm/pd_hybrid/user_config.json
```
#### 2、配置
no_proxy中需要加上后端模型服务所在服务器地址（比如10.10.10.10）
配置Coordinate配置文件地址
```
export no_proxy=127.0.0.1,localhost,local,.local,10.10.10.10
# 需要配置文件的绝对路径
export USER_CONFIG_PATH="/XXX/MindIE-PyMotor/examples/infer_engines/vllm/pd_hybrid/user_config.json"
```
#### 3、启动pymotor服务
```
nohup python -m motor.coordinator.main > ../motor.log 2>&1 &
```
#### 4、启动后端vllm服务
判断coordinate是否启动成功
```
# 应返回 ready:true
curl -s http://127.0.0.1:1026/readiness
```
启动成功后，启动后端vllm服务（注意，如果是p实例，端口号需要从30000开始，如果是d实例，端口号需要从40000开始，如果是pd混部，端口号需要从50000开始）,下面以PD混部为例
```
nohup vllm serve /data/Qwen3.5-0.8b \
--host 0.0.0.0 \
--port 50000 \
--tensor-parallel-size 1 \
--data-parallel-size 1 \
--max-model-len 16384 \
--max-num-batched-tokens 16384 \
--gpu-memory-utilization 0.9 \
--trust-remote-code \
--additional-config '{"enable_cpu_binding":true}' \
--compilation-config '{"cudagraph_mode":"FULL_DECODE_ONLY"}' \
--async-scheduling > ../vllm-server.log 2>&1 &
```

#### 5、注册实例到Coordinator
```
python scripts/refresh_instance.py --union-list 1
```
预期输出
```
请求成功！
响应内容：
XXX
配置更新完成！
```

#### 6、验证服务
```
curl 127.0.0.1:1999/v1/chat/completions \
-H "Content-Type: application/json" \
-d ' {
"model": "qwen",
"messages": [{
    "role": "user",
    "content": "你是谁?"
}],
"agent_hint": {
    "session_id": "sub-1",
    "parent_session_id": "main-0",
    "cache_control": {"type": "ephemeral", "ttl": 5},
    "context_management": {
        "edits": [{"type": "offload", "start": 6, "end": 9, "target": "messages/tools"}],
        "evicts": [{"type": "offload", "start": 6, "end": 9, "target": "messages/tools"}]
    },
    "latency_control": {"latency_sensitivity": 20},
    "priority_control": {"priority": 1}
}
}'
```