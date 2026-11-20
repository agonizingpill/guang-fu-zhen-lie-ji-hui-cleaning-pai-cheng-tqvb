import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker,DeclarativeBase
DATABASE_URL=os.getenv('DATABASE_URL','mysql+pymysql://solar:solar@db:3306/solar')
# MySQL 需要显式 READ COMMITTED 以在锁内看到前一笔已提交许可；SQLite 仅用于本地测试，不支持该隔离级别。
_engine_options={'pool_pre_ping':True}
if not DATABASE_URL.startswith('sqlite'):_engine_options['isolation_level']='READ COMMITTED'
engine=create_engine(DATABASE_URL,**_engine_options)
Session=sessionmaker(engine,expire_on_commit=False)
class Base(DeclarativeBase):pass
def session():
    with Session() as db:yield db
