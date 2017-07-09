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
        