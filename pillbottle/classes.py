from .schema import CronEntry, Channel, User
from dateutil import parser
import asyncio
import discord
from croniter import croniter
import time
from datetime import datetime
import pytz

# to fix a discord bug
class MessageSender:
    def __init__(self, bot, channel, message):
        self.bot = bot
        self.channel = channel
        self.message = message
        self.sent = False
        
    async def __call__(self):
        print("Trying to send message", self.sent)
        if(not self.sent):
            self.sent = True
            await self.bot.send_message(self.channel, self.message)

class RegexChecker:
    def __init__(self, qre):
        self.qre = qre

    def __call__(self, message):
        self.match = self.qre.search(message.content)
        print("Check:", self.match)
        return self.match is not None

localtz = pytz.timezone("America/New_York")        
class DateChecker:
    
    def __call__(self, message):
        return self.checktime(message.content)
            
    def checktime(self, msg):
        try:
            self.datetime = parser.parse(msg)
            return True
        except ValueError:
            return False
            
    def get_crontab(self):
        utcnow = datetime.utcnow()
        tzoffset = localtz.utcoffset(utcnow)
        dt = self.datetime - tzoffset
        return "{} {} * * *".format(dt.minute, dt.hour)
        

class Question:
    
    def __init__(self, txt, channel, done_cb=None, filters={}):
        self.text = txt
        self.cb = done_cb
        self.timeout = None
        
        print("Question", channel)
        self.channel = channel
        self.filters = filters
        
    async def ask(self, bot):
    
        print("Asking", self.channel)
        
        if self.text:
            self.message = await bot.send_message(self.channel, self.text)
        
        self.future = bot.loop.create_task(bot.wait_for_message(**self.filters))
        
        if self.cb is not None:
            self.future.add_done_callback(self.cb)
        
        return self.future
        
    def process_response(self, response):
        return None
        
    def timed_out(self):
        pass
        
class ServerQuestion(Question):

    def __init__(self, ctx, *args, **kwargs):
        self.ctx = ctx
        self.response = None
        super().__init__(*args, **kwargs)
        

    def process_response(self, response):
        print("ServerQuestion response", self.response, self.ctx)
        if self.response is not None:    
            coro = self.ctx.bot.send_message(self.ctx.message.channel, self.response)
            return self.ctx.bot.loop.create_task(coro)
            
        return None
        
class ListQuestion(Question):
    
    def __init__(self, txt, channel, choices=[], vfun=lambda v: v, done_cb=None, filters={}):
        
        print("ListQuestion choices", choices)
        
        txt += "\n"
        txt += "\n".join(["{}: {}".format(i,vfun(choices[i])) for i in range(len(choices))])
        
        self.choices = choices
        self.selected = None
        
        if "check" in filters:
            check = filters["check"]
            filters["check"] = lambda msg: self.check(msg) and check(msg)
        else:
            filters["check"] = self.check
        
        super().__init__(txt, channel, done_cb=done_cb, filters=filters)
        
    def check(self, msg):
        try:
            i = int(msg.content)
            if i >= len(self.choices):
                return False
                
            self.selected = self.choices[i]
            return True
        except ValueError:
            return False        
        

class Conversation:

    def __init__(self, bot, first, timeout=None):
        print("Conversation")
        self.bot = bot
        self.timeout = timeout
        self.question = first
        
    async def run(self):
        print("Running")
        
        try:
            while self.question is not None:
                self.current_future = await self.question.ask(self.bot)
                try:
                    current_future = None
                    print("timeout", self.question.timeout)
                    response = await asyncio.wait_for(self.current_future, self.question.timeout)
                
                    if self.question is not None:
                        current_future = self.question.process_response(response)
                
                except asyncio.TimeoutError:
                    self.question.timed_out()
                    
                print(type(current_future))
                if type(current_future) == asyncio.Future:
                    self.current_future = current_future
                    await asyncio.wait_for(self.current_future, None)
        except asyncio.CancelledError:
            return
        
    async def cancel(self):
        self.current_future.cancel()
        
class SetupConvo(Conversation):

    def __init__(self, ctx, timeout=None):
        print("Reminder")
        self.ctx = ctx
        self.dc = DateChecker()
        filters = {"author": ctx.message.author,
        "channel": ctx.message.channel, 
        "check": self.dc}
        
        print(ctx.message.channel)
        
        q = Question("Reminders are daily.  What time would you like to be reminded?", 
        channel=ctx.message.channel,
        done_cb=self.timeResponse, 
        filters=filters)
        
        super().__init__(ctx.bot, q, timeout)
    
    #def __init__(self, txt, channel, done_cb=None, filters={}):
    def timeResponse(self, future):
        filters = {"author": self.ctx.message.author, "channel": self.ctx.message.channel}
    
        self.question = ServerQuestion(self.ctx, 
        "Which server do you want to notify you for extra reminders?",
        self.ctx.message.channel,
        done_cb=self.serverResponse,
        filters=filters)
        
    def serverResponse(self, future):
        reply = future.result()
        dest_server = discord.utils.find(lambda s : s.name == reply.content, self.ctx.bot.servers)
        
        if dest_server is None:
            self.question.response = "I don't have access to {}.".format(reply.content)
            return
            
        self.server = dest_server
        
        botmember = discord.utils.find(lambda m: m.id == self.ctx.bot.user.id, dest_server.members)
        member = discord.utils.find(lambda m : m.id == self.ctx.message.author.id, dest_server.members)
        
        if member is None:
            self.question.response = "You're not a member of {}.".format(reply.content)
            return
            
        possible_channels = [channel for channel in dest_server.channels if channel.permissions_for(member).read_messages and channel.permissions_for(botmember).send_messages and channel.type == discord.ChannelType.text]
        
        if len(possible_channels) == 0:
            self.question.response = "You can't read any messages of channels that I can send to in {}...".format(reply.content)
            return
        
        print("Possible Channels", possible_channels)
        
        #def __init__(self, txt, channel, choices=[], vfun=lambda v: v, done_cb=None, filters={}):
        filters = {"channel": self.ctx.message.channel, "author": self.ctx.message.author}
        
        self.question = ListQuestion("Select a channel:", 
        self.ctx.message.channel, 
        choices=possible_channels, 
        vfun=lambda c : c.name, 
        done_cb=self.channelResponse,
        filters=filters)
        
    def channelResponse(self, future):
        self.channel = self.question.selected
        self.question = None
        
    def getNewEntry(self, message, db):
        '''
        _channelid = Column("channelid", String, ForeignKey('channels.id'))
        _userid = Column('userid', String, ForeignKey('users.id'))
        message = Column(String, nullable=False)
        timeout = Column(Integer)
        requestcount = Column(Integer)
        _echannel = Column("echannel", String, ForeignKey('channels.id'))
        cron = Column(String, nullable=False)
        response = Column(String, nullable=False)
        next_run = Column(Float)
        '''
        uchan = db.query(Channel).filter_by(id=self.ctx.message.channel.id).first()
        if uchan is None:
            serverid = None if self.ctx.message.server is None else self.ctx.message.server.id
            servername = None if serverid is None else self.ctx.message.server.name
            uchan = Channel(id=self.ctx.message.channel.id, name=self.ctx.message.channel.name, serverid=serverid, servername=servername)
            db.add(uchan)
            
        u = db.query(User).filter_by(id=self.ctx.message.author.id).first()
        if u is None:
            u = User(id=self.ctx.message.author.id, name=self.ctx.message.author.name)
            db.add(u)
            
        echan = db.query(Channel).filter_by(id=self.channel.id).first()
        if echan is None:
            echan = Channel(id=self.channel.id, name=self.channel.name, serverid=self.channel.server.id, servername=self.channel.server.name)
            db.add(echan)
        
        cron = self.dc.get_crontab()
        citer = croniter(cron, time.time())
    
        centry = CronEntry(channelid=uchan.id, 
        userid=u.id,
        message=message, 
        timeout=5, 
        requestcount=3, 
        echannel=self.channel.id, 
        response="Thank you!",
        cron=cron,
        next_run=citer.get_next(float))
        
        db.add(centry)
        db.commit()
        
        return centry
        
class ReminderQuestion(Question):

    #def __init__(self, txt, channel, done_cb=None, filters={}):
    def __init__(self, centry, db, done_cb=None, filters={}):
    
        self.centry = centry
        self.remaining = centry.requestcount
        self.db = db
        super().__init__(None, None, done_cb, filters)
        
        t = time.time()
        dt = t if self.centry.next_run is None else self.centry.next_run - 1
        self.croniter = croniter(centry.cron, start_time=dt)
        
        print(t, self.centry.next_run, t - self.centry.next_run)
        self.centry.next_run = self.croniter.get_next(float)
        while self.centry.next_run < t:
            self.centry.next_run = self.croniter.get_next(float)
            
        self.db.commit()
    
        self.timeout = self.centry.next_run - t
        
        print("Next run", self.timeout, datetime.fromtimestamp(self.centry.next_run), datetime.fromtimestamp(t), centry.cron)
        
    async def wait_for_discord(self):
        await self.centry.wait_for_discord()
        self.filters["author"] = self.centry.user
        self.filters["channel"] = self.channel = self.centry.channel
        self.filters["check"] = self.command_check
        
        self.extra_mention = self.centry.user.name
        member = discord.utils.find(lambda m : m.id == self.centry.user.id, self.centry.everyone.server.members)
        if member is not None:
            self.extra_mention = member.mention
        
    def timed_out(self):
        self.remaining -= 1
        if self.remaining >= 0:
            print("Remind")
            self.timeout = self.centry.timeout
            self.text = self.centry.message
        else:
            print("Extra remind")
            
            '''
            self.remaining = self.centry.requestcount
            self.centry.next_run = self.croniter.get_next(float)
            self.db.commit()
            self.text = None
            '''
            self.reset()
            self.timeout = self.centry.next_run - time.time()
            
            text = "Please remind {}: {}".format(self.extra_mention, self.centry.message)
            coro = self.centry.bot.send_message(self.centry.everyone, text)
            asyncio.ensure_future(coro)
            
    def process_response(self, reply):
        
        prev = self.croniter.get_prev(datetime)
        skipped = prev > reply.timestamp
        self.croniter.get_next(datetime)
        fut = None
        if not skipped:
            fut = self.centry.bot.loop.create_task(self.centry.bot.send_message(self.centry.channel, self.centry.response))
            self.reset()
            
        self.timeout = self.centry.next_run - time.time()
        print("process_response: next_run", self.timeout, self.centry.next_run, datetime.fromtimestamp(self.centry.next_run))
        print("skipped", skipped, prev)
        return fut
        
    def command_check(self, message):
        return not message.content.startswith(self.centry.bot.command_prefix)
        
    def reset(self):
        self.remaining = self.centry.requestcount
        self.centry.next_run = self.croniter.get_next(float)
        self.db.add(self.centry)
        self.db.commit()
        self.text = None
        
class ReminderConvo(Conversation):

    def __init__(self, centry, db):
        self.centry = centry
        self.remaining = centry.requestcount
        self.bot = centry.bot
        
        q = ReminderQuestion(centry, db)
        super().__init__(self.bot, q)
        
    async def run(self):
        # TODO: use async/futures, so immediately cancellable
        await self.question.wait_for_discord()
        await super().run()
        
    def callback(self, future):
        pass
        #self.timeout = self.centry.timeout
        #print("Callback", future.result())
        
            
class Action:

    def __init__(self, bot, channel, msg, everyone=None, requests=3, timeout=900, response="Thank you!"):
        self.bot = bot
        self.channel = channel
        self.message = msg
        self.timeout = timeout
        self.requests = requests
        self.everyone = everyone
        self.response = response

    async def __call__(self):
        print("Action")
        def checkfun(msg1):
            
            def check(msg2):
                print(msg1.author, msg2.author)
                return msg1.author != msg2.author
            
            return check
        
        for i in range(self.requests):
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
            
    def getDbObj(self, db):
        
        uchan = db.query(Channel).filter_by(id=self.channel.id).first()
        if uchan is None:
            uchan = Channel(id=self.channel.id, serverid=None)
            db.add(uchan)
            
        echan = db.query(Channel).filter_by(id=self.everyone.id).first()
        if echan is None:
            echan = Channel(id=self.everyone.id, serverid=self.everyone.server.id)
            db.add(echan)
            
        dbobj = CronEntry(channelid=uchan.id, message=self.message, timeout=self.timeout, requestcount=self.requests, echannel=echan.id, response=self.response)
        return dbobj
        