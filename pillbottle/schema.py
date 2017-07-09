#schema

SQLALCHEMY_DATABASE_URI = 'sqlite:///pillbottle.db'
SQL_DEBUG = True

#import sqlalchemy
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, ForeignKey, Integer, String, Date, Float, Boolean

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
    channelid = Column(String, ForeignKey('channels.id'))
    message = Column(String, nullable=False)
    timeout = Column(Integer)
    requestcount = Column(Integer)
    echannel = Column(String, ForeignKey('channels.id'))
    cron = Column(String, nullable=False)
    response = Column(String, nullable=False)

    @property
    def bot(self):
        return self.bot
        
    @bot.setter
    def bot(self, value):
        
        self.bot = value
        self.channel = self.bot.get_user_info(self.channelid)
        self.everyone = self.bot.get_channel(self.echannel)
        
        
    def __call__(self):
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
        
Base.metadata.create_all(engine)
