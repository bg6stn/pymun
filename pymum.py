import threading
import time
from pymumble_py3 import Mumble
from pymumble_py3.callbacks import PYMUMBLE_CLBK_TEXTMESSAGERECEIVED, PYMUMBLE_CLBK_SOUNDRECEIVED
import pyaudio
import numpy as np
import audioop
import queue
import collections

class MumbleClient:
    def __init__(self, host, port=64738, username="PythonClient", password=""):
        """初始化Mumble客户端"""
        self.host = 'bg6stn.top'
        self.port = 64738
        self.username = 'AAA'
        self.password = 'hjc757'
        
        # 初始化Mumble连接
        self.mumble = None
        self.connected = False
        
        # 音频相关配置
        self.audio_format = pyaudio.paInt16
        self.audio_channels = 1
        self.audio_rate = 48000  # Mumble默认采样率
        self.audio_chunk = 1024
        
        # 音频设备设置
        self.input_device_index = None
        self.output_device_index = None
        self.audio_interface = None
        
        # 音频输入输出流
        self.audio_input_stream = None
        self.audio_output_stream = None
        
        # 线程控制
        self.audio_send_thread = None
        self.audio_receive_thread = None
        self.running = False
        
        # 文本消息回调函数列表
        self.text_message_callbacks = []
        
        # 音频处理 - 改为使用队列和缓冲区字典
        self.audio_queues = {}  # 每个用户一个队列
        self.mixed_audio_buffer = collections.deque(maxlen=10)  # 混合音频缓冲区
        self.buffer_size = 5
        
        # 音频设置
        self.microphone_enabled = False
        
        # 音频处理参数
        self.max_volume_threshold = 32767  # 16位音频的最大值
        self.silence_threshold = 80  # 静音阈值
        self.clipping_threshold = 100000  # 削波阈值（调高以适应高灵敏度麦克风）
        
    def list_audio_devices(self):
        """列出所有音频设备"""
        if self.audio_interface is None:
            self.audio_interface = pyaudio.PyAudio()
            
        print("\n" + "="*60)
        print("音频设备列表")
        print("="*60)
        
        info = self.audio_interface.get_host_api_info_by_index(0)
        num_devices = info.get('deviceCount')
        
        input_devices = []
        output_devices = []
        
        for i in range(num_devices):
            device_info = self.audio_interface.get_device_info_by_host_api_device_index(0, i)
            
            # 检查设备是否支持输入
            if device_info.get('maxInputChannels') > 0:
                input_devices.append((i, device_info))
            
            # 检查设备是否支持输出
            if device_info.get('maxOutputChannels') > 0:
                output_devices.append((i, device_info))
        
        print("\n输入设备 (麦克风):")
        print("-" * 40)
        for i, info in input_devices:
            print(f"{i}: {info['name']} (输入通道: {info['maxInputChannels']}, 默认采样率: {int(info['defaultSampleRate'])})")
        
        print("\n输出设备 (扬声器/耳机):")
        print("-" * 40)
        for i, info in output_devices:
            print(f"{i}: {info['name']} (输出通道: {info['maxOutputChannels']}, 默认采样率: {int(info['defaultSampleRate'])})")
        
        return input_devices, output_devices
    
    def test_input_device(self, device_index):
        """测试输入设备 - 调整音量阈值"""
        try:
            print(f"\n测试输入设备 {device_index}...")
            print("注意：高灵敏度麦克风可能会显示高音量，这不一定表示失真")
            
            # 创建测试录音
            stream = self.audio_interface.open(
                format=self.audio_format,
                channels=self.audio_channels,
                rate=self.audio_rate,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=self.audio_chunk
            )
            
            frames = []
            max_rms = 0
            clipping_count = 0
            
            print("录音中... 请用正常音量说话（3秒）")
            
            # 录制3秒钟的音频
            for i in range(0, int(self.audio_rate / self.audio_chunk * 3)):
                data = stream.read(self.audio_chunk, exception_on_overflow=False)
                frames.append(data)
                
                # 分析音频质量
                rms = audioop.rms(data, 2)
                max_rms = max(max_rms, rms)
                
                # 检查削波
                audio_array = np.frombuffer(data, dtype=np.int16)
                if np.max(np.abs(audio_array)) > 32000:  # 接近最大值表示可能削波
                    clipping_count += 1
                
                # 显示音量指示
                normalized_rms = min(rms / 1000, 20)
                bar = "█" * int(normalized_rms)
                spaces = " " * (20 - len(bar))
                print(f"\r音量: [{bar}{spaces}] {rms:5d}", end="")
            
            print("\n录音完成")
            
            stream.stop_stream()
            stream.close()
            
            # 分析结果
            print(f"\n分析结果:")
            print(f"最大音量: {max_rms}")
            print(f"削波次数: {clipping_count}")
            
            if max_rms < 100:
                print("⚠️  音量过低，请检查麦克风连接或调整麦克风增益")
                retry = input("是否重试？(y/n, 默认y): ").strip().lower()
                if retry in ('', 'y', 'yes'):
                    return self.test_input_device(device_index)
                return False
            elif clipping_count > 10:
                print("⚠️  检测到削波失真，建议降低麦克风增益")
                retry = input("是否继续使用此设备？(y/n, 默认y): ").strip().lower()
                if retry in ('', 'y', 'yes'):
                    print("✅ 设备测试通过（注意可能有轻微失真）")
                    return True
                return False
            else:
                print("✅ 设备测试通过")
                return True
                
        except Exception as e:
            print(f"❌ 设备测试失败: {e}")
            return False
    
    def test_output_device(self, device_index):
        """测试输出设备"""
        try:
            print(f"\n测试输出设备 {device_index}...")
            
            # 生成更柔和的测试音
            duration = 1.5  # 1.5秒
            frequency = 440  # A4音
            t = np.linspace(0, duration, int(self.audio_rate * duration), False)
            
            # 添加淡入淡出避免爆音
            fade_samples = int(0.1 * self.audio_rate)  # 100ms淡入淡出
            envelope = np.ones(len(t))
            envelope[:fade_samples] = np.linspace(0, 1, fade_samples)
            envelope[-fade_samples:] = np.linspace(1, 0, fade_samples)
            
            samples = np.sin(2 * np.pi * frequency * t) * envelope
            audio_data = (samples * 16000).astype(np.int16).tobytes()  # 降低音量
            
            stream = self.audio_interface.open(
                format=self.audio_format,
                channels=self.audio_channels,
                rate=self.audio_rate,
                output=True,
                output_device_index=device_index,
                frames_per_buffer=self.audio_chunk
            )
            
            print("播放测试音...")
            stream.write(audio_data)
            
            stream.stop_stream()
            stream.close()
            
            response = input("您是否听到了清晰的音调？(y/n, 默认y): ").strip().lower()
            if response in ('', 'y', 'yes'):
                print("✅ 输出设备测试通过")
                return True
            else:
                print("❌ 输出设备可能有问题")
                return False
            
        except Exception as e:
            print(f"❌ 设备测试失败: {e}")
            return False
    
    def select_audio_devices(self):
        """让用户选择音频设备"""
        print("正在初始化音频设备...")
        self.audio_interface = pyaudio.PyAudio()
        
        while True:
            input_devices, output_devices = self.list_audio_devices()
            
            print("\n请选择音频设备 (输入 'q' 退出):")
            
            # 选择输入设备
            while True:
                try:
                    choice = input("\n选择输入设备编号 (默认回车使用系统默认设备): ").strip()
                    if choice == '':
                        self.input_device_index = None
                        print("使用默认输入设备")
                        break
                    elif choice.lower() == 'q':
                        return False
                    else:
                        device_index = int(choice)
                        if any(i == device_index for i, _ in input_devices):
                            if self.test_input_device(device_index):
                                self.input_device_index = device_index
                                break
                            else:
                                print("设备测试失败，请重新选择")
                        else:
                            print("无效的设备编号，请重新选择")
                except ValueError:
                    print("请输入有效的数字")
            
            # 选择输出设备
            while True:
                try:
                    choice = input("\n选择输出设备编号 (默认回车使用系统默认设备): ").strip()
                    if choice == '':
                        self.output_device_index = None
                        print("使用默认输出设备")
                        break
                    elif choice.lower() == 'q':
                        return False
                    else:
                        device_index = int(choice)
                        if any(i == device_index for i, _ in output_devices):
                            if self.test_output_device(device_index):
                                self.output_device_index = device_index
                                break
                            else:
                                print("设备测试失败，请重新选择")
                        else:
                            print("无效的设备编号，请重新选择")
                except ValueError:
                    print("请输入有效的数字")
            
            # 确认选择
            confirm = input("\n确认使用这些设备？(y/n, 默认y): ").strip().lower()
            if confirm in ('', 'y', 'yes'):
                print("✅ 音频设备选择完成")
                return True
            else:
                print("重新选择设备...")
    
    def connect(self):
        """连接到Mumble服务器"""
        # 首先选择音频设备
        if not self.select_audio_devices():
            print("音频设备选择取消")
            return False
            
        try:
            # 创建Mumble实例
            self.mumble = Mumble(self.host, self.username, password=self.password, port=self.port)
            
            # 启用音频接收
            self.mumble.set_receive_sound(1)
            
            # 连接到服务器
            self.mumble.start()
            self.mumble.is_ready()
            
            self.connected = True
            print(f"成功连接到Mumble服务器: {self.host}:{self.port}")
            print(f"当前用户ID: {self.mumble.users.myself_session}")
            
            # 注册回调函数
            self.mumble.callbacks.set_callback(PYMUMBLE_CLBK_TEXTMESSAGERECEIVED, self._on_text_message)
            self.mumble.callbacks.set_callback(PYMUMBLE_CLBK_SOUNDRECEIVED, self._on_sound_received)
            
            # 启动音频处理
            self.start_audio()
            
            return True
        except Exception as e:
            print(f"连接Mumble服务器失败: {str(e)}")
            self.connected = False
            return False
    
    def disconnect(self):
        """断开与Mumble服务器的连接"""
        if self.connected:
            self.stop_audio()
            self.mumble.stop()
            self.connected = False
            print("已断开与Mumble服务器的连接")
        
        if self.audio_interface:
            self.audio_interface.terminate()
    
    def send_text_message(self, message, channel_id=None, user_id=None):
        """发送文本消息"""
        if not self.connected:
            print("未连接到服务器，无法发送消息")
            return False
            
        try:
            if user_id:
                self.mumble.users[user_id].send_text_message(message)
            elif channel_id:
                self.mumble.channels[channel_id].send_text_message(message)
            else:
                self.mumble.channels[self.mumble.users.myself['channel_id']].send_text_message(message)
            return True
        except Exception as e:
            print(f"发送消息失败: {str(e)}")
            return False
    
    def _on_text_message(self, text_message):
        """内部文本消息处理函数"""
        try:
            message_data = {
                "message": text_message.message,
                "sender": self.mumble.users[text_message.actor]['name'],
                "sender_id": text_message.actor,
                "channel_id": text_message.channel_id,
                "timestamp": time.time()
            }
            
            for callback in self.text_message_callbacks:
                try:
                    callback(message_data)
                except Exception as e:
                    print(f"文本消息回调执行失败: {str(e)}")
        except Exception as e:
            print(f"处理文本消息时出错: {str(e)}")
    
    def _on_sound_received(self, user, sound_data):
        """音频接收回调函数 - 改进多人同时说话处理"""
        try:
            if user.get_property('session') == self.mumble.users.myself_session:
                return
                
            if sound_data and hasattr(sound_data, 'pcm') and len(sound_data.pcm) > 0:
                user_id = user.get_property('session')
                
                # 为每个用户创建独立的队列
                if user_id not in self.audio_queues:
                    self.audio_queues[user_id] = queue.Queue(maxsize=10)
                
                try:
                    # 非阻塞方式添加音频数据
                    self.audio_queues[user_id].put_nowait(sound_data.pcm)
                except queue.Full:
                    # 队列已满，丢弃最旧的数据
                    try:
                        self.audio_queues[user_id].get_nowait()
                        self.audio_queues[user_id].put_nowait(sound_data.pcm)
                    except queue.Empty:
                        pass
                    
        except Exception as e:
            print(f"处理接收音频时出错: {e}")
    
    def _mix_audio(self, audio_chunks):
        """混合多个音频流"""
        if not audio_chunks:
            return None
            
        # 将所有音频数据转换为numpy数组
        audio_arrays = []
        max_length = 0
        
        for chunk in audio_chunks:
            if len(chunk) % 2 == 0:  # 确保是完整的16位数据
                audio_array = np.frombuffer(chunk, dtype=np.int16)
                audio_arrays.append(audio_array)
                max_length = max(max_length, len(audio_array))
        
        if not audio_arrays:
            return None
            
        # 混合音频
        mixed = np.zeros(max_length, dtype=np.int16)
        count = np.zeros(max_length, dtype=np.int16)
        
        for audio_array in audio_arrays:
            # 确保长度一致
            if len(audio_array) < max_length:
                padded = np.pad(audio_array, (0, max_length - len(audio_array)), 'constant')
            else:
                padded = audio_array[:max_length]
            
            # 累加音频数据
            mixed = mixed + padded
            count[:len(padded)] += 1
        
        # 平均混合，防止削波
        non_zero = count > 0
        mixed[non_zero] = mixed[non_zero] / count[non_zero]
        mixed = np.clip(mixed, -32768, 32767).astype(np.int16)
        
        return mixed.tobytes()
    
    def register_text_callback(self, callback):
        """注册文本消息回调函数"""
        if callable(callback) and callback not in self.text_message_callbacks:
            self.text_message_callbacks.append(callback)
            return True
        return False
    
    def unregister_text_callback(self, callback):
        """移除已注册的文本消息回调函数"""
        if callback in self.text_message_callbacks:
            self.text_message_callbacks.remove(callback)
            return True
        return False
    
    def start_audio(self):
        """启动音频发送和接收线程"""
        if not self.connected:
            print("未连接到服务器，无法启动音频")
            return False
            
        self.running = True
        
        # 启动音频接收线程
        self.audio_receive_thread = threading.Thread(target=self._receive_audio, daemon=True)
        self.audio_receive_thread.start()
        
        print("音频处理已启动")
        return True
    
    def stop_audio(self):
        """停止音频处理"""
        self.running = False
        
        if self.audio_input_stream:
            self.audio_input_stream.stop_stream()
            self.audio_input_stream.close()
            self.audio_input_stream = None
        
        if self.audio_output_stream:
            self.audio_output_stream.stop_stream()
            self.audio_output_stream.close()
            self.audio_output_stream = None
        
        if self.audio_send_thread and self.audio_send_thread.is_alive():
            self.audio_send_thread.join(timeout=1.0)
        
        if self.audio_receive_thread and self.audio_receive_thread.is_alive():
            self.audio_receive_thread.join(timeout=1.0)
        
        print("音频处理已停止")
    
    def _send_audio(self):
        """音频发送线程函数 - 添加音频处理"""
        try:
            self.audio_input_stream = self.audio_interface.open(
                format=self.audio_format,
                channels=self.audio_channels,
                rate=self.audio_rate,
                input=True,
                input_device_index=self.input_device_index,
                frames_per_buffer=self.audio_chunk
            )
            
            print("音频发送线程已启动 - 麦克风已启用")
            
            if self.mumble.sound_output is None:
                for i in range(50):
                    if self.mumble.sound_output is not None or not self.running:
                        break
                    time.sleep(0.1)
            
            if self.mumble.sound_output is None:
                print("错误: sound_output未初始化")
                return
            
            while self.running and self.connected and self.microphone_enabled:
                try:
                    data = self.audio_input_stream.read(self.audio_chunk, exception_on_overflow=False)
                    
                    # 音频处理：音量标准化和限制
                    audio_array = np.frombuffer(data, dtype=np.int16)
                    
                    # 计算RMS音量
                    rms = np.sqrt(np.mean(audio_array.astype(np.float32)**2))
                    
                    if rms > self.silence_threshold:
                        # 简单的压缩处理，防止削波
                        max_val = np.max(np.abs(audio_array))
                        if max_val > self.clipping_threshold:
                            scale_factor = self.clipping_threshold / max_val * 0.8
                            audio_array = (audio_array * scale_factor).astype(np.int16)
                            data = audio_array.tobytes()
                        
                        self.mumble.sound_output.add_sound(data)
                    
                    sleep_time = self.audio_chunk / self.audio_rate
                    time.sleep(sleep_time)
                    
                except Exception as e:
                    print(f"读取音频数据失败: {e}")
                    time.sleep(0.1)
                
        except Exception as e:
            print(f"音频发送错误: {str(e)}")
        finally:
            if self.audio_input_stream:
                self.audio_input_stream.stop_stream()
                self.audio_input_stream.close()
                self.audio_input_stream = None
            print("音频发送线程已停止")
    
    def _receive_audio(self):
        """音频接收线程函数 - 改进多人同时说话处理"""
        try:
            self.audio_output_stream = self.audio_interface.open(
                format=self.audio_format,
                channels=self.audio_channels,
                rate=self.audio_rate,
                output=True,
                output_device_index=self.output_device_index,
                frames_per_buffer=self.audio_chunk
            )
            
            print("音频接收线程已启动")
            
            while self.running and self.connected:
                try:
                    # 收集所有用户的音频数据
                    audio_chunks = []
                    
                    for user_id in list(self.audio_queues.keys()):
                        try:
                            # 非阻塞获取音频数据
                            audio_data = self.audio_queues[user_id].get_nowait()
                            audio_chunks.append(audio_data)
                        except queue.Empty:
                            continue
                    
                    # 混合音频
                    if audio_chunks:
                        mixed_audio = self._mix_audio(audio_chunks)
                        if mixed_audio:
                            self.audio_output_stream.write(mixed_audio)
                    else:
                        # 没有音频数据时短暂休眠
                        time.sleep(0.005)  # 更短的休眠提高响应性
                        
                except Exception as e:
                    print(f"音频混合错误: {e}")
                    time.sleep(0.01)
                
        except Exception as e:
            print(f"音频接收错误: {str(e)}")
        finally:
            if self.audio_output_stream:
                self.audio_output_stream.stop_stream()
                self.audio_output_stream.close()
                self.audio_output_stream = None
            print("音频接收线程已停止")
    
    def set_speaking(self, speaking=True):
        """设置说话状态"""
        if self.connected:
            try:
                if speaking:
                    if not self.microphone_enabled:
                        self.microphone_enabled = True
                        if self.audio_send_thread is None or not self.audio_send_thread.is_alive():
                            self.audio_send_thread = threading.Thread(target=self._send_audio, daemon=True)
                            self.audio_send_thread.start()
                    
                    self.mumble.users.myself.unmute()
                    print("麦克风已开启 - 现在可以说话")
                else:
                    self.microphone_enabled = False
                    self.mumble.users.myself.mute()
                    print("麦克风已静音")
            except Exception as e:
                print(f"设置说话状态失败: {e}")

# 示例用法
if __name__ == "__main__":
    def handle_received_message(message):
        print(f"\n收到来自 {message['sender']} 的消息: {message['message']}")
    
    client = MumbleClient("bg6stn.top", username="AAA")
    client.register_text_callback(handle_received_message)
    
    if client.connect():
        try:
            print("连接成功！可以开始语音聊天了。")
            print("输入消息进行文本聊天")
            print("输入 'mic on' 开启麦克风")
            print("输入 'mic off' 关闭麦克风")
            print("输入 'exit' 退出程序")
            
            while True:
                message = input("\n请输入命令或消息: ")
                if message.lower() == 'exit':
                    break
                elif message.lower() == 'mic on':
                    client.set_speaking(True)
                elif message.lower() == 'mic off':
                    client.set_speaking(False)
                else:
                    client.send_text_message(message)
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\n正在断开连接...")
        finally:
            client.disconnect()
