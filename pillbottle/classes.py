from .schema import CronEntry, Channel
from dateutil import parser

class RegexChecker:
    def __init__(self, qre):
        self.qre = qre

    def __call__(self, message):
        self.match = self.qre.search(message.content)
        print("Check:", self.match)
        return self.match is not None
        
class DateChecker:
    
    def __call__(self, message):
        return self.checktime(message.content)
            
    def checktime(self, msg):
        try:
            self.datetime = parser.parse(msg)
            return True
        except ValueError:
            return False

class Question:
    
    def __init__(self, txt, channel, done_cb=None, filters={}):
        self.text = txt
        self.cb = cb
        self.channel = channel
        self.filters = filters
        
    async def ask(self, bot):
        self.message = await bot.send_message(self.channel, self.txt)
        self.future = bot.loop.create_task(bot.wait_for_message(**self.filters))
        
        if self.cb is not None:
            self.future.add_done_callback(self.cb)
        return self.future
        
    async def process_response(self, response):
        return None
        
class ServerQuestion(Question):

    def __init__(self, ctx, *args, **kwargs):
        self.ctx = ctx
        self.response = None
        super().__init__(args, kwargs)
        

    async def process_response(self, response):
    
        if self.response is not None:    
            coro = ctx.bot.send_message(ctx.message.channel, self.response)
            return ctx.bot.loop.create_task(coro)
            
        return None
        
class ListQuestion(Question):
    
    def __init__(self, txt, channel, choices=[], vfun=lambda v: v, done_cb=None, filters={}):
        self.text = txt + "\n"
        self.text += "\n".join(["{}: {}".format(i,vfun(choices[i])) for i in len(choices)])
        self.choices = choices
        self.selected = None
        
        if "check" in filters:
            check = filters["check"]
            filters["check"] = lambda msg: self.check(msg) and check(msg)
        else:
            filters["check"] = self.check
        
        super().__init__(txt, channel, done_cb, filters)
        
    def check(self, msg):
        try:
            i = int(msg.content)
            if i >= len(self.choices):
                return False
                
            self.selected = choices[i]
            return True
        except ValueError:
            return False
        
        

class Conversation:

    def __init__(self, bot, first, timeout=None):
        self.bot = bot
        self.timeout = timeout
        self.question = first

    async def run(self):
        
        while self.question is not None:
            self.current_future = await self.question.ask(self.bot)
            response = await asyncio.wait_for(self.current_future, self.timeout)
            current_future = self.bot.loop.create_task(self.question.process_response(response))
            
            if type(current_future) == asyncio.Future:
                self.current_future = current_future
                await asyncio.wait_for(self.current_future, self.timeout)
        
    async def cancel(self):
        self.current_future.cancel()
        
class ReminderConvo(Conversation):

    def __init__(self, ctx, timeout=None):
        
        self.ctx = ctx
        self.dc = DateChecker()
        filters = {"author": ctx.message.author,
        "channel": ctx.message.channel, 
        "check": dc}
        
        q = Question("Reminders are daily.  What time would you like to be reminded?", 
        ctx.message.channel,
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
        
        #def __init__(self, txt, channel, choices=[], vfun=lambda v: v, done_cb=None, filters={}):
        filters = {"channel": ctx.message.channel, "author": ctx.message.author}
        
        self.question = ListQuestion("Select a channel:", 
        self.ctx.message.channel, 
        choices=possible_channels, 
        vfun=lambda c : c.name, 
        done_cb=self.channelResponse,
        filters=filters)
        
    def channelResponse(self, future)
        self.channel = self.question.selected
        self.question = None
        
        
            
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
        