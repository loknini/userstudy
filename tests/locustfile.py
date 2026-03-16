"""
Locust 压力测试脚本
用于测试 User Study 平台的性能

运行方式:
1. 启动应用: python run.py
2. 运行测试: locust -f locustfile.py --host=http://localhost:8888
3. 打开浏览器访问: http://localhost:8089
"""

from locust import HttpUser, task, between, events
from locust.runners import MasterRunner
import random
import json
import time


class StudyUser(HttpUser):
    """模拟用户行为"""
    
    # 用户行为间隔: 5-15秒（模拟真实用户思考时间）
    wait_time = between(5, 15)
    
    def on_start(self):
        """用户启动时执行 - 创建参与者"""
        self.participant_id = None
        self.current_question = 0
        self.total_questions = 0
        
        # 开始实验，获取 participant_id
        with self.client.post("/start", catch_response=True, allow_redirects=False) as response:
            if response.status_code == 303:
                # 从重定向 URL 中提取 participant_id
                location = response.headers.get("location", "")
                if "pid=" in location:
                    self.participant_id = location.split("pid=")[1]
                    response.success()
                else:
                    response.failure("No participant ID in redirect")
            else:
                response.failure(f"Failed to start study: {response.status_code}")
    
    @task(3)
    def view_question(self):
        """查看问题页面（权重: 3）"""
        if not self.participant_id:
            return
        
        # 随机查看当前题目或下一题
        qidx = self.current_question
        
        with self.client.get(
            f"/question/{qidx}",
            params={"pid": self.participant_id},
            catch_response=True,
            name="/question/[id]"
        ) as response:
            if response.status_code == 200:
                # 检查是否包含问题内容
                if "option" in response.text or "选择" in response.text:
                    response.success()
                else:
                    response.failure("Question content not found")
            elif response.status_code == 302 or response.status_code == 303:
                # 可能已完成所有题目
                response.success()
            else:
                response.failure(f"Failed to load question: {response.status_code}")
    
    @task(2)
    def submit_answer(self):
        """提交答案（权重: 2）"""
        if not self.participant_id:
            return
        
        qidx = self.current_question
        question_id = f"q{qidx + 1}-1"  # 模拟问题ID
        
        # 随机选择一个选项 (0-3)
        selected_index = random.randint(0, 3)
        
        start_time = time.time()
        
        with self.client.post(
            f"/submit/{qidx}",
            data={
                "participant_id": self.participant_id,
                "question_id": question_id,
                "selected_index": str(selected_index),
                "time_spent": str(random.uniform(3, 10))  # 模拟答题用时 3-10秒
            },
            catch_response=True,
            allow_redirects=False,
            name="/submit/[id]"
        ) as response:
            elapsed = time.time() - start_time
            
            if response.status_code == 303:
                location = response.headers.get("location", "")
                
                if "/completed" in location:
                    # 完成所有题目
                    response.success()
                    self.current_question = 0  # 重置，模拟新用户
                elif "/question/" in location:
                    # 进入下一题
                    response.success()
                    self.current_question += 1
                    
                    # 记录答题耗时
                    if elapsed > 5:
                        print(f"Slow answer submission: {elapsed:.2f}s")
                else:
                    response.success()
            elif response.status_code in [400, 422]:
                # 业务逻辑错误（如无效参数）
                response.success()  # 不算系统错误
            else:
                response.failure(f"Submit failed: {response.status_code}")
    
    @task(1)
    def view_index(self):
        """访问首页（权重: 1）"""
        with self.client.get("/", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Index failed: {response.status_code}")


class QuickUser(HttpUser):
    """快速用户 - 模拟快速答题的用户"""
    
    wait_time = between(1, 3)  # 快速答题，间隔1-3秒
    
    def on_start(self):
        """快速开始实验"""
        self.participant_id = None
        self.current_question = 0
        
        with self.client.post("/start", catch_response=True, allow_redirects=False) as response:
            if response.status_code == 303:
                location = response.headers.get("location", "")
                if "pid=" in location:
                    self.participant_id = location.split("pid=")[1]
                    response.success()
    
    @task(10)
    def quick_submit(self):
        """快速提交答案"""
        if not self.participant_id:
            return
        
        qidx = self.current_question
        
        with self.client.post(
            f"/submit/{qidx}",
            data={
                "participant_id": self.participant_id,
                "question_id": f"q{qidx + 1}-1",
                "selected_index": str(random.randint(0, 3)),
                "time_spent": str(random.uniform(1, 3))
            },
            catch_response=True,
            allow_redirects=False,
            name="/submit/[id] (quick)"
        ) as response:
            if response.status_code == 303:
                if "/completed" in response.headers.get("location", ""):
                    self.current_question = 0
                else:
                    self.current_question += 1
                response.success()
            else:
                response.failure(f"Quick submit failed: {response.status_code}")


class AdminUser(HttpUser):
    """管理员用户 - 模拟后台操作"""
    
    wait_time = between(10, 30)  # 管理员操作间隔较长
    
    def on_start(self):
        """管理员不需要创建 participant"""
        self.admin_pass = "admin"  # 默认密码
    
    @task(5)
    def view_stats(self):
        """查看统计数据"""
        with self.client.get(
            "/admin/stats",
            params={"pw": self.admin_pass},
            catch_response=True,
            name="/admin/stats"
        ) as response:
            if response.status_code == 200:
                try:
                    data = response.json()
                    if "total_participants" in data:
                        response.success()
                    else:
                        response.failure("Invalid stats format")
                except:
                    response.failure("Invalid JSON response")
            elif response.status_code == 401:
                response.success()  # 认证失败是正常业务逻辑
            else:
                response.failure(f"Stats failed: {response.status_code}")
    
    @task(2)
    def export_data(self):
        """导出数据"""
        with self.client.get(
            "/admin/export.csv",
            params={"pw": self.admin_pass},
            catch_response=True,
            name="/admin/export.csv"
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 401:
                response.success()
            else:
                response.failure(f"Export failed: {response.status_code}")
    
    @task(1)
    def view_admin_page(self):
        """访问管理后台页面"""
        with self.client.get(
            "/admin",
            params={"pw": self.admin_pass},
            catch_response=True,
            name="/admin"
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 401:
                response.success()
            else:
                response.failure(f"Admin page failed: {response.status_code}")


# 自定义事件监听
@events.request.add_listener
def on_request(request_type, name, response_time, response_length, 
               response, context, exception, **kwargs):
    """记录慢请求"""
    if response_time > 2000:  # 超过2秒的请求
        print(f"⚠️  Slow request: {request_type} {name} took {response_time}ms")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """测试结束时输出统计"""
    print("\n" + "=" * 50)
    print("压力测试完成！")
    print("=" * 50)
    
    if environment.runner and hasattr(environment.runner, 'stats'):
        stats = environment.runner.stats
        print(f"\n总请求数: {stats.total.num_requests}")
        print(f"失败数: {stats.total.num_failures}")
        print(f"平均响应时间: {stats.total.avg_response_time:.2f}ms")
        print(f"95%响应时间: {stats.total.get_response_time_percentile(0.95):.2f}ms")
        print(f"RPS: {stats.total.total_rps:.2f}")
