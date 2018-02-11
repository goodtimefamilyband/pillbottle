#schema

# TODO: Change to serverid

SQLALCHEMY_DATABASE_URI = 'sqlite:///pillbottle.db'
SQL_DEBUG = False

#import sqlalchemy
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy import Column, ForeignKey, Integer, String, Date, Float, Boolean

import asyncio
import aiocron
import discord

Base = declarative_base()
engine = create_engine(SQLALCHEMY_DATABASE_URI, echo=SQL_DEBUG)

Session = sessionmaker(bind=engine)
db = Session()

class DiscordBase:

    '''
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.event = asyncio.Event()
    '''   

    @property
    def bot(self):
        try:
            return self._bot
        except AttributeError:
            return None
            
    @bot.setter
    def bot(self, value):
        self._bot = value
        self.task = self._bot.loop.create_task(self._discord_init())
        
    @property
    def discord(self):
        try:
            return self._discord
        except AttributeError:
            return None
        
    async def _discord_init(self):
        self._discord = await self.load_discord()
    
    async def wait_for_discord(self):
        await asyncio.wait_for(self.task, None)
            
    async def load_discord(self):
        return None
            

class Channel(Base, DiscordBase):
    __tablename__ = 'channels'
    
    id = Column(String, primary_key=True)
    serverid = Column(String)
    name = Column(String)
    servername = Column(String)
    
    async def load_discord(self):
        channel = self.bot.get_channel(self.id)
        if channel is None and self.user is not None:
            channel = await self.bot.start_private_message(self.user)
            
        return self.bot.get_channel(self.id)
    
class User(Base, DiscordBase):
    __tablename__ = 'users'
    
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    
    async def load_discord(self):
        return await self.bot.get_user_info(self.id)
        
class Role(Base, DiscordBase):
    __tablename__ = 'roles'
    
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    servername = Column(String, nullable=False)
    
    async def load_discord(self):
        server = discord.utils.find(lambda s : s.name == self.servername, self.bot.servers)
        if server is None:
            return None
            
        return discord.utils.find(lambda r : r.id == self.id, server.roles)

class CronEntry(Base):
    __tablename__ = 'entries'
    
    id = Column(Integer, primary_key=True)
    channelid = Column("channelid", String, ForeignKey('channels.id'))
    userid = Column('userid', String, ForeignKey('users.id'))
    message = Column(String, nullable=False)
    timeout = Column(Integer)
    requestcount = Column(Integer)
    echannel = Column("echannel", String, ForeignKey('channels.id'))
    roleid = Column("roleid", String, ForeignKey("roles.id"))
    cron = Column(String, nullable=False)
    next_run = Column(Float)
    passphrase = Column(String)
    
    @property
    def bot(self):
        try:
            return self._bot
        except AttributeError:
            return None
        
    @bot.setter
    def bot(self, value):
        print("setbot", self.userid, self.channelid, self.echannel)
        self._bot = value
        
        self._user = db.query(User).filter_by(id=self.userid).first()
        self._channel = db.query(Channel).filter_by(id=self.channelid).first()
        self._everyone = db.query(Channel).filter_by(id=self.echannel).first()
        self._role = db.query(Role).filter_by(id=self.roleid).first()
        
        self._user.bot = self._bot
    
    async def wait_for_discord(self):
        if self._user.discord is None:
            await self._user.wait_for_discord()
        
        self._channel.user = self._user.discord
        
        if self._channel.discord is None:
            self._channel.bot = self._bot
            await self._channel.wait_for_discord()
        
        if self._everyone.discord is None:
            self._everyone.bot = self._bot
            await self._everyone.wait_for_discord()
            
        if self._role is not None and self._role.discord is None:
            self._role.bot = self.bot
            await self._role.wait_for_discord()
        
    def load_dbchannel_by_discord_channel(self, value):
        dbchan = db.query(Channel).filter_by(id=value.id).first()
        if dbchan is None:
            dbchan = Channel(id=value.id, name=value.name)
            
            try:
                if value.server is not None:
                    dbchan.serverid = value.server.id
                    dbchan.servername = value.server.name
            except AttributeError:
                pass
                    
            db.add(dbchan)
            db.commit()
            
        dbchan._discord = value
        return dbchan
        
    def load_dbrole_by_discord_role(self, value):
        dbrole = db.query(Role).filter_by(id=value.id).first()
        if dbrole is None:
            dbrole = Role(id=value.id, name=value.name, servername=value.server.name)
            db.add(dbrole)
            db.commit()
            
        dbrole._discord = value
        return dbrole
        
    @property
    def channel(self):
        return self._channel.discord
        
    @channel.setter
    def channel(self, value):
        self._channel = self.load_dbchannel_by_discord_channel(value)
        self.channelid = value.id
        
    @property
    def everyone(self):
        return self._everyone.discord
        
    @everyone.setter
    def everyone(self, value):
        self._everyone = self.load_dbchannel_by_discord_channel(value)
        self.echannel = value.id
        
    @property
    def user(self):
        return self._user.discord
        
    @user.setter
    def user(self, value):
        dbuser = db.query(User).filter_by(id=value.id).first()
        if dbuser is None:
            dbuser = User(id=value.id, name=value.name)    
            db.add(dbuser)
            db.commit()
            
        self.userid = dbuser.id
        dbuser._discord = value
        self._user = dbuser
        
    @property
    def role(self):
        try:
            if self._role is None:
                return None
            else:
                return self._role.discord
        except AttributeError:
            return None
        
    @role.setter
    def role(self, value):
        if value is None:
            self._role = None
        else:
            self._role = self.load_dbrole_by_discord_role(value)
            self.roleid = value.id
    
class Response(Base):
    
    __tablename__ = "responses"
    
    id = Column(Integer, primary_key=True)
    entryid = Column(Integer, ForeignKey('entries.id'), primary_key=True)
    text = Column(String, nullable=False)
        
Base.metadata.create_all(engine)
