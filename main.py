import time
from pymum import MumbleClient

class SimpleMumble:
    def __init__(self, server, username, password=""):
        """初始化Mumble客户端
        Args:
            server: 服务器地址
            username: 用户名
            password: 密码（可选，默认为空）
        """
        self.client = MumbleClient(server, username=username, password=password)
        self.client.register_text_callback(self._print_msg)
        self.is_connected = False
    
    def _print_msg(self, msg):
        """消息处理函数"""
        time_str = time.strftime("%H:%M:%S", time.localtime(msg['timestamp']))
        print(f"[{time_str}] {msg['sender']}: {msg['message']}")
        print(f"{msg['message']}")
        if f"{msg['message']}"=='micon':
            mumble.mic(True)
            #print('麦克风已开启')
        elif f"{msg['message']}"=='micoff':
            mumble.mic(False)
            #print('麦克风已关闭') 
    def start(self):
        """启动连接"""
        if self.client.connect():
            self.client.set_speaking(False)  # 默认关闭麦克风
            self.is_connected = True
            print("Mumble连接成功！")
            return True
        else:
            print("Mumble连接失败！")
            return False
    
    def send(self, text):
        """发送消息"""
        if self.is_connected:
            success = self.client.send_text_message(text)
            if success:
                print(f"消息发送成功: {text}")
            else:
                print(f"消息发送失败: {text}")
            return success
        else:
            print("未连接到服务器，无法发送消息")
            return False
    
    def mic(self, on_off):
        """控制麦克风
        Args:
            on_off: True开启，False关闭
        """
        if self.is_connected:
            self.client.set_speaking(on_off)
            status = "开启" if on_off else "关闭"
            print(f"麦克风{status}")
        else:
            print("未连接到服务器，无法控制麦克风")
    
    def stop(self):
        """停止连接"""
        if self.is_connected:
            self.client.disconnect()
            self.is_connected = False
            print("Mumble连接已关闭")

# 使用示例 - 无密码服务器
if __name__ == "__main__":
    # 创建实例（密码为空）
    mumble = SimpleMumble("bg6stn.top", "AAA", password="")
    
    if mumble.start():
        # 发送消息
        mumble.send("Hello World!")
        
        # 开启麦克风
        mumble.mic(True)
        
        time.sleep(3)
        
        # 关闭麦克风
        mumble.mic(False)
        
        # 再发送一条消息
        mumble.send("测试消息发送！")
        mumble.send("mic on")
        # 保持运行，持续接收消息
        print("程序运行中，按 Ctrl+C 退出...")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("正在退出...")
        finally:
            mumble.stop()
