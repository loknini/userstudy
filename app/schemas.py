"""
Pydantic Schemas - 数据验证和序列化
"""
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator


# ==================== 基础响应模型 ====================

class ResponseBase(BaseModel):
    """基础响应模型"""
    success: bool = True
    message: str = "success"
    data: Optional[Any] = None


class ErrorResponse(BaseModel):
    """错误响应模型"""
    success: bool = False
    message: str
    error_code: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


# ==================== 参与者相关 ====================

class ParticipantCreate(BaseModel):
    """创建参与者请求"""
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    
    # 新增：更多用户特征（用于分析，不去重）
    screen_resolution: Optional[str] = None  # 如 "1920x1080"
    language: Optional[str] = None  # 如 "zh-CN"
    timezone: Optional[str] = None  # 如 "Asia/Shanghai"
    platform: Optional[str] = None  # 如 "Win32", "MacIntel"
    cookies_enabled: Optional[str] = None  # "true" / "false"
    do_not_track: Optional[str] = None  # "1" / "0" / "unspecified"


class ParticipantOut(BaseModel):
    """参与者输出模型"""
    id: str
    started_at: datetime
    ip_address: Optional[str] = None
    completed_at: Optional[datetime] = None
    response_count: int = 0
    is_completed: bool = False
    
    model_config = {"from_attributes": True}


class ParticipantDetail(ParticipantOut):
    """参与者详情（含响应）"""
    responses: List["ResponseOut"] = []


# ==================== 响应相关 ====================

class AnswerSubmit(BaseModel):
    """提交答案请求"""
    participant_id: str = Field(..., min_length=36, max_length=36)
    question_id: str = Field(..., min_length=1, max_length=50)
    selected_index: int = Field(..., ge=0, le=10)
    rating: Optional[int] = Field(None, ge=1, le=5)
    comment: Optional[str] = Field(None, max_length=1000)
    time_spent: Optional[float] = Field(None, ge=0)
    
    @field_validator('time_spent')
    @classmethod
    def validate_time_spent(cls, v: Optional[float]) -> Optional[float]:
        """验证答题时间合理性（最多30分钟）"""
        if v is not None and v > 1800:  # 30分钟 = 1800秒
            return 1800
        return v


class ResponseOut(BaseModel):
    """响应输出模型"""
    id: int
    participant_id: str
    question_id: str
    selected_index: Optional[int]
    rating: Optional[int]
    comment: Optional[str]
    time_spent: Optional[float]
    created_at: datetime
    
    model_config = {"from_attributes": True}


class AnswerResult(BaseModel):
    """答题结果"""
    success: bool
    next_question_idx: Optional[int] = None
    is_completed: bool = False
    message: str


# ==================== 研究配置相关 ====================

class ExampleConfig(BaseModel):
    """示例配置"""
    text: str
    images: List[str]


class QuestionConfig(BaseModel):
    """问题配置"""
    id: str = Field(..., min_length=1, max_length=50)
    prompt: str
    images: List[str] = Field(..., min_length=2, max_length=10)
    models: List[str] = Field(default_factory=list)
    type: str = Field(default="choose_one", pattern="^(choose_one|choose_multiple|rating)$")


class StudyConfigData(BaseModel):
    """研究配置数据结构"""
    title: str = Field(..., min_length=1, max_length=200)
    instructions: str = Field(..., min_length=1)
    randomize: bool = Field(default=True)
    examples: List[ExampleConfig] = Field(default_factory=list)
    questions: List[QuestionConfig] = Field(..., min_length=1)
    
    @field_validator('questions')
    @classmethod
    def validate_questions(cls, v: List[QuestionConfig]) -> List[QuestionConfig]:
        """验证问题ID唯一性"""
        ids = [q.id for q in v]
        if len(ids) != len(set(ids)):
            raise ValueError("问题ID必须唯一")
        return v


class StudyConfigOut(BaseModel):
    """研究配置输出"""
    id: int
    version: str
    uploaded_at: datetime
    is_active: bool
    config: StudyConfigData  # 解析后的配置
    
    model_config = {"from_attributes": True}


class StudyConfigUpload(BaseModel):
    """上传配置响应"""
    success: bool
    config_id: int
    version: str
    question_count: int


# ==================== 统计数据相关 ====================

class QuestionStats(BaseModel):
    """单个问题统计"""
    question_id: str
    prompt: str
    total_responses: int
    picks_by_index: Dict[int, int]  # 索引 -> 选择次数
    picks_by_model: Dict[str, int]  # 模型名 -> 选择次数
    average_time_spent: Optional[float]


class ModelStats(BaseModel):
    """模型统计"""
    model_name: str
    total_picks: int
    emotion_picks: int  # 情感维度
    content_picks: int  # 内容维度
    pick_rate: float  # 选择率


class OverallStats(BaseModel):
    """整体统计"""
    total_participants: int
    completed_participants: int
    completion_rate: float
    total_responses: int
    average_response_time: Optional[float]
    per_question: List[QuestionStats]
    per_model: List[ModelStats]


class ChartData(BaseModel):
    """图表数据"""
    labels: List[str]
    data: List[int]


class ChartDataSet(BaseModel):
    """图表数据集"""
    overall_votes: ChartData
    emotion_votes: ChartData
    content_votes: ChartData


# ==================== 导出相关 ====================

class ExportTask(BaseModel):
    """导出任务"""
    task_id: str
    status: str  # pending, processing, completed, failed
    created_at: datetime
    completed_at: Optional[datetime] = None
    file_url: Optional[str] = None
    message: Optional[str] = None


# ==================== 页面渲染数据 ====================

class IndexPageData(BaseModel):
    """首页数据"""
    title: str
    instructions: str
    examples: List[ExampleConfig]


class QuestionPageData(BaseModel):
    """问题页面数据"""
    title: str
    qidx: int
    total_questions: int
    question_id: str
    prompt: str
    images: List[tuple]  # [(path, index), ...]
    participant_id: str
    progress_percent: float


# ==================== Zip 上传相关 ====================

class ZipImageInfo(BaseModel):
    """Zip 包中单张图片的信息"""
    filename: str
    size_bytes: int
    width: int = 0
    height: int = 0


class ZipPromptInfo(BaseModel):
    """Zip 包中单个 prompt 的信息"""
    name: str
    file_count: int
    images: List[ZipImageInfo]


class MethodCandidate(BaseModel):
    """方法候选"""
    source: str       # 文件名中提取的原始标识符
    method: str       # 确认后的方法名
    variant: Optional[str] = None  # 变体名
    confidence: str = "high"  # high / uncertain / low
    present_in: int = 0  # 出现在几个 prompt 中


class MethodAnalysisResult(BaseModel):
    """方法分析结果"""
    candidates: List[MethodCandidate]
    missing_matrix: Dict[str, List[str]] = {}


class ZipUploadResponse(BaseModel):
    """上传 zip 后的分析响应"""
    upload_id: str
    emotion: str
    emotion_cn: str = ""
    prompt_count: int
    prompts: List[ZipPromptInfo]
    method_analysis: MethodAnalysisResult
    total_size_mb: float = 0.0


class ConfirmMethod(BaseModel):
    """确认/提交时的单个方法映射"""
    source: str
    method: str
    variant: Optional[str] = None


class ConfirmZipRequest(BaseModel):
    """确认 zip 并生成问卷的请求"""
    upload_id: str
    study_name: str = ""
    study_code: str = ""
    emotion: str
    description: str = ""
    instructions: str = ""
    title: str = "User Study"
    prompt_translations: Dict[str, str] = {}
    emotion_cn: str = ""
    question_types: List[str] = ["emotion", "content"]
    save_translations: bool = True
    methods: List[ConfirmMethod]
    image_settings: Dict[str, Any] = {}
    duplicate_action: str = "rename"  # rename / overwrite / abort


class ConfirmZipResponse(BaseModel):
    """确认 zip 生成的问卷响应"""
    success: bool = True
    study: Dict[str, Any]
    processed_images: int = 0
    skipped_images: int = 0
    total_size_mb: float = 0.0


class DuplicateInfo(BaseModel):
    """重名问卷信息"""
    code: str
    name: str
    created_at: str


class LlmTranslateRequest(BaseModel):
    """LLM 翻译请求"""
    prompts: List[str]


class TranslationBatchUpdate(BaseModel):
    """批量更新翻译词条请求"""
    translations: Dict[str, Optional[str]]


# 解决循环引用
ParticipantDetail.model_rebuild()
