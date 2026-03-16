"""
Pytest 配置和共享夹具
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app.config import Settings, get_settings


# 使用内存数据库进行测试
TEST_DATABASE_URL = "sqlite:///:memory:"

@pytest.fixture(scope="session")
def engine():
    """创建测试数据库引擎"""
    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def db_session(engine):
    """为每个测试函数创建新的数据库会话"""
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="function")
def client(db_session):
    """创建测试客户端，使用测试数据库"""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    # 替换数据库依赖
    app.dependency_overrides[get_db] = override_get_db
    
    with TestClient(app) as test_client:
        yield test_client
    
    # 清理依赖覆盖
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def test_config():
    """测试配置数据"""
    return {
        "title": "Test Study",
        "instructions": "Test instructions",
        "randomize": False,
        "examples": [],
        "questions": [
            {
                "id": "q1-1",
                "prompt": "Question 1 emotion",
                "images": ["/static/test1.jpg", "/static/test2.jpg"],
                "models": ["model1", "model2"],
                "type": "choose_one"
            },
            {
                "id": "q1-2",
                "prompt": "Question 1 content",
                "images": ["/static/test1.jpg", "/static/test2.jpg"],
                "models": ["model1", "model2"],
                "type": "choose_one"
            },
            {
                "id": "q2-1",
                "prompt": "Question 2 emotion",
                "images": ["/static/test3.jpg", "/static/test4.jpg"],
                "models": ["model1", "model2"],
                "type": "choose_one"
            }
        ]
    }


@pytest.fixture(scope="function")
def mock_study_config(db_session, test_config):
    """模拟加载研究配置"""
    from app.services.study import StudyService
    from app.schemas import StudyConfigData
    
    service = StudyService(db_session)
    config_data = StudyConfigData(**test_config)
    service.save_config(config_data, uploaded_by="test")
    db_session.commit()
    
    return test_config


@pytest.fixture(scope="function")
def test_study(db_session, test_config):
    """创建测试问卷（使用自动生成短代码）"""
    from app.services.study import StudyService
    from app.schemas import StudyConfigData
    
    service = StudyService(db_session)
    config_data = StudyConfigData(**test_config)
    
    # 不指定 custom_code，让系统自动生成唯一代码
    study = service.create_study(
        name="Test Study",
        config_data=config_data,
        description="Test study for unit tests"
    )
    db_session.commit()
    
    return study


@pytest.fixture(scope="function")
def test_participant_with_study(db_session, test_study):
    """创建关联到测试问卷的参与者"""
    from app.services.study import StudyService
    from app.schemas import ParticipantCreate
    
    service = StudyService(db_session)
    data = ParticipantCreate(
        ip_address="127.0.0.1",
        user_agent="Test Browser"
    )
    participant = service.create_participant(data, study_id=test_study.id)
    db_session.commit()
    
    return participant
