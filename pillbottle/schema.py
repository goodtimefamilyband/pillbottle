#schema

SQLALCHEMY_DATABASE_URI = 'sqlite:///pillbottle.db'
SQL_DEBUG = True

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

class Channel(Base):
    __tablename__ = 'channels'
    
    id = Column(String, primary_key=True)
    serverid = Column(String)

class CronEntry(Base):
    __tablename__ = 'entries'
    
    id = Column(Integer, primary_key=True)
    _channelid = Column("channelid", String, ForeignKey('channels.id'))
    message = Column(String, nullable=False)
    timeout = Column(Integer)
    requestcount = Column(Integer)
    _echannel = Column("echannel", String, ForeignKey('channels.id'))
    cron = Column(String, nullable=False)
    response = Column(String, nullable=False)

    @property
    def bot(self):
        try:
            return self._bot
        except AttributeError:
            return None
        
    @bot.setter
    def bot(self, value):
        
        self._bot = value
        self.channel = self.bot.get_user_info(self.channelid)
        self.everyone = self.bot.get_channel(self.echannel)
        
    @property
    def channel(self):
        return self._channel
        
    @channel.setter
    def channel(self, value):
        
        if not asyncio.iscoroutine(value):
            self._channel = value
            return
            
        self._channel = yield from value
        
        
    @property
    def everyone(self):
        return self._everyone
        
    @everyone.setter
    def everyone(self, value):
        if not asyncio.iscoroutine(value):
            self._everyone = value
            return
            
        self._everyone = yield from value
        
    @hybrid_property
    def channelid(self):
        return self._channelid
        
    @channelid.setter
    def channelid(self, value):
        self._channelid = value
        
        if self.bot is not None:
            self.channel = self.bot.get_user_info(self.channelid)
            
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
            message = await self.bot.send_message(self.channel, self.message)
            print(message.channel.id, self.channel.id)
            reply = await self.bot.wait_for_message(channel=message.channel, timeout=self.timeout, check=checkfun(message))
            if reply is not None:
                #print(reply.content)
                await self.bot.send_message(self.channel, self.response)
                return
              
        if self.everyone is not None:
            await self.bot.send_message(self.everyone, "@everyone please remind {}: {}".format(self.channel.mention, self.message))
            
    def schedule(self):
        self.crontab = aiocron.crontab(self.cron, func=self, loop=self.bot.loop)
        
Base.metadata.create_all(engine)
