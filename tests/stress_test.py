"""
简化的压力测试脚本（无需 Locust Web 界面）
适合快速测试和 CI/CD 集成

使用方法:
    python stress_test.py --host http://localhost:8888 --users 50 --duration 60
"""

import argparse
import time
import random
import statistics
from collections import defaultdict
import requests
import threading


class StressTester:
    """压力测试器"""
    
    def __init__(self, host: str, num_users: int, duration: int):
        self.host = host.rstrip('/')
        self.num_users = num_users
        self.duration = duration
        self.results = defaultdict(list)
        self.errors = defaultdict(int)
        self.stop_event = threading.Event()
        
    def make_request(self, method: str, endpoint: str, **kwargs) -> dict:
        """执行单个请求"""
        url = f"{self.host}{endpoint}"
        start_time = time.time()
        
        try:
            if method == "GET":
                response = requests.get(url, timeout=10, **kwargs)
            else:
                response = requests.post(url, timeout=10, **kwargs)
            
            elapsed = (time.time() - start_time) * 1000  # 转换为毫秒
            
            return {
                'status_code': response.status_code,
                'elapsed': elapsed,
                'success': 200 <= response.status_code < 400
            }
        except Exception as e:
            return {
                'status_code': 0,
                'elapsed': (time.time() - start_time) * 1000,
                'success': False,
                'error': str(e)
            }
    
    def user_session(self, user_id: int):
        """模拟单个用户会话"""
        participant_id = None
        
        while not self.stop_event.is_set():
            try:
                # 1. 开始实验
                result = self.make_request(
                    "POST", "/start", 
                    allow_redirects=False
                )
                self.results['start'].append(result)
                
                if not result['success'] or result['status_code'] != 303:
                    continue
                
                # 模拟用户答题（3-5题）
                num_questions = random.randint(3, 5)
                
                for qidx in range(num_questions):
                    if self.stop_event.is_set():
                        break
                    
                    # 查看问题页面
                    time.sleep(random.uniform(2, 5))  # 思考时间
                    
                    result = self.make_request(
                        "GET", 
                        f"/question/{qidx}",
                        params={"pid": f"user_{user_id}"}
                    )
                    self.results['question'].append(result)
                    
                    # 提交答案
                    time.sleep(random.uniform(1, 3))
                    
                    result = self.make_request(
                        "POST",
                        f"/submit/{qidx}",
                        data={
                            "participant_id": f"user_{user_id}",
                            "question_id": f"q{qidx + 1}-1",
                            "selected_index": str(random.randint(0, 3)),
                            "time_spent": str(random.uniform(2, 8))
                        },
                        allow_redirects=False
                    )
                    self.results['submit'].append(result)
                
                # 用户完成后休息一下
                time.sleep(random.uniform(5, 10))
                
            except Exception as e:
                self.errors['user_session'] += 1
                time.sleep(1)
    
    def run(self):
        """运行压力测试"""
        print("=" * 60)
        print(f"开始压力测试")
        print(f"目标: {self.host}")
        print(f"并发用户数: {self.num_users}")
        print(f"测试时长: {self.duration}秒")
        print("=" * 60)
        print()
        
        # 启动用户线程
        threads = []
        start_time = time.time()
        
        for i in range(self.num_users):
            t = threading.Thread(target=self.user_session, args=(i,))
            t.daemon = True
            t.start()
            threads.append(t)
            
            # 逐步增加用户（每0.5秒启动一个）
            time.sleep(0.5)
        
        print(f"✓ 已启动 {self.num_users} 个用户线程")
        print(f"✓ 测试运行中... (按 Ctrl+C 提前结束)\n")
        
        # 等待测试完成
        try:
            while time.time() - start_time < self.duration:
                elapsed = int(time.time() - start_time)
                if elapsed % 10 == 0:  # 每10秒打印进度
                    total_requests = sum(len(v) for v in self.results.values())
                    print(f"进度: {elapsed}/{self.duration}秒 | "
                          f"总请求: {total_requests}")
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n收到中断信号，正在停止...")
        
        # 停止所有线程
        self.stop_event.set()
        for t in threads:
            t.join(timeout=2)
        
        # 生成报告
        self.generate_report()
    
    def generate_report(self):
        """生成测试报告"""
        print("\n" + "=" * 60)
        print("压力测试报告")
        print("=" * 60)
        
        total_requests = 0
        total_success = 0
        total_failures = 0
        all_times = []
        
        for endpoint, results in self.results.items():
            if not results:
                continue
            
            times = [r['elapsed'] for r in results]
            success_count = sum(1 for r in results if r['success'])
            failure_count = len(results) - success_count
            
            total_requests += len(results)
            total_success += success_count
            total_failures += failure_count
            all_times.extend(times)
            
            print(f"\n【{endpoint.upper()}】")
            print(f"  请求数: {len(results)}")
            print(f"  成功: {success_count} | 失败: {failure_count}")
            print(f"  成功率: {(success_count/len(results)*100):.1f}%")
            
            if times:
                print(f"  平均响应: {statistics.mean(times):.2f}ms")
                print(f"  最小响应: {min(times):.2f}ms")
                print(f"  最大响应: {max(times):.2f}ms")
                if len(times) > 1:
                    print(f"  中位数: {statistics.median(times):.2f}ms")
                    print(f"  95%分位: {sorted(times)[int(len(times)*0.95)]:.2f}ms")
        
        print("\n" + "-" * 60)
        print(f"总计:")
        print(f"  总请求数: {total_requests}")
        print(f"  总成功: {total_success}")
        print(f"  总失败: {total_failures}")
        print(f"  总成功率: {(total_success/total_requests*100):.1f}%" if total_requests > 0 else "  N/A")
        
        if all_times:
            total_time = self.duration
            rps = total_requests / total_time if total_time > 0 else 0
            print(f"  RPS: {rps:.2f}")
            print(f"  平均响应时间: {statistics.mean(all_times):.2f}ms")
            print(f"  95%响应时间: {sorted(all_times)[int(len(all_times)*0.95)]:.2f}ms")
        
        if self.errors:
            print(f"\n错误统计:")
            for error_type, count in self.errors.items():
                print(f"  {error_type}: {count}")
        
        print("\n" + "=" * 60)


def main():
    parser = argparse.ArgumentParser(description='User Study 压力测试')
    parser.add_argument('--host', default='http://localhost:8888',
                        help='目标主机地址 (默认: http://localhost:8888)')
    parser.add_argument('--users', type=int, default=20,
                        help='并发用户数 (默认: 20)')
    parser.add_argument('--duration', type=int, default=60,
                        help='测试时长/秒 (默认: 60)')
    
    args = parser.parse_args()
    
    tester = StressTester(args.host, args.users, args.duration)
    tester.run()


if __name__ == "__main__":
    main()
