#schema

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

Base = declarative_base()
engine = create_engine(SQLALCHEMY_DATABASE_URI, echo=SQL_DEBUG)

Session = sessionmaker(bind=engine)
objDb = Session()    

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
    

class CronEntry(Base):
    __tablename__ = 'entries'
    
    id = Column(Integer, primary_key=True)
    channelid = Column("channelid", String, ForeignKey('channels.id'))
    userid = Column('userid', String, ForeignKey('users.id'))
    message = Column(String, nullable=False)
    timeout = Column(Integer)
    requestcount = Column(Integer)
    echannel = Column("echannel", String, ForeignKey('channels.id'))
    cron = Column(String, nullable=False)
    response = Column(String, nullable=False)
    next_run = Column(Float)

    
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
        
        self._user = objDb.query(User).filter_by(id=self.userid).first()
        self._channel = objDb.query(Channel).filter_by(id=self.channelid).first()
        self._everyone = objDb.query(Channel).filter_by(id=self.echannel).first()
        
        self._user.bot = self._bot
    
    async def wait_for_discord(self):
        await self._user.wait_for_discord()
        self._channel.user = self._user.discord
        
        self._channel.bot = self._bot
        self._everyone.bot = self._bot
        
        await self._channel.wait_for_discord()
        await self._everyone.wait_for_discord()
        
    @property
    def channel(self):
        return self._channel.discord
        
    @property
    def everyone(self):
        return self._everyone.discord
        
    @property
    def user(self):
        return self._user.discord
    '''    
    @property
    async def channel(self):
        
        try:
            self._channel = await asyncio.wait_for(self.channel_task, None)
        except AttributeError:
            pass
            
        return self._channel
        
    @channel.setter
    def channel(self, value):
        
        if not asyncio.iscoroutine(value):
            self._channel = value
            return
            
        try:
            del self._channel
        except AttributeError:
            pass
            
        self.channel_task = self.bot.loop.create_task(value)
    
    @property
    async def user(self):
        
        try:
            return self._user
        except AttributeError:
            pass
            
        try:
            self._user = await asyncio.wait_for(self.user_task, None)
        except AttributeError:
            pass
            
        return self._user
        
    @user.setter
    def user(self, value):
        
        if not asyncio.iscoroutine(value):
            self._user = value
            return
            
        try:
            del self._user
        except AttributeError:
            pass
            
        self.user_task = self.bot.loop.create_task(value)
        
        
    @property
    async def everyone(self):
        try:
            self._everyone = await asyncio.wait_for(self.everyone_task, None)
        except AttributeError:
            pass
            
        return self._everyone
        
    @everyone.setter
    def everyone(self, value):
        if not asyncio.iscoroutine(value):
            self._everyone = value
            return
        
        try:
            del self._everyone
        except AttributeError:
            pass
            
        self.everyone_task = self.bot.loop.create_task(value)
        
    @hybrid_property
    def userid(self):
        return self._userid
        
    @userid.setter
    def userid(self, value):
        self._userid = value
        
        if self.bot is not None:
            self.user = self.bot.get_user_info(self._userid)
            
        
    @hybrid_property
    def channelid(self):
        return self._channelid
        
    @channelid.setter
    def channelid(self, value):
        self._channelid = value
        
        if self.bot is not None:
            self.channel = self.bot.get_channel(self.channelid)
            
    @hybrid_property
    def echannel(self):
        return self._echannel
        
    @echannel.setter
    def echannel(self, value):
        self._echannel = value
        
        if self.bot is not None:
            self.everyone = self.bot.get_channel(self.echannel)
        
    async def __call__(self):
        if self.bot is None:
            return
            
        print("Action")
        def checkfun(msg1):
            
            def check(msg2):
                print(msg1.author, msg2.author)
                return msg1.author != msg2.author
            
            return check
        
        for i in range(self.requestcount):
            #print(i)
            channel = await self.channel
            everyone = await self.everyone
            message = await self.bot.send_message(channel, self.message)
            #print(message.channel.id, self.channel.id)
            reply = await self.bot.wait_for_message(channel=message.channel, timeout=self.timeout, check=checkfun(message))
            if reply is not None:
                #print(reply.content)
                await self.bot.send_message(channel, self.response)
                return
              
        if everyone is not None:
            await self.bot.send_message(everyone, "@everyone please remind {}: {}".format(channel.mention, self.message))
            
    def schedule(self):
        self.crontab = aiocron.crontab(self.cron, func=self, loop=self.bot.loop)
        
    def setChannelAsync(self, future):
        self._channel = future.result()
        
    '''
        
Base.metadata.create_all(engine)
