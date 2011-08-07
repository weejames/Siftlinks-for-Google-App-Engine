#!/usr/bin/env python

import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'settings'

from google.appengine.dist import use_library
use_library('django', '1.2')

import oauth
import urllib
import random
import string
import hashlib
import logging

from datetime import datetime
from google.appengine.api import taskqueue
from google.appengine.ext import webapp
from google.appengine.ext.webapp import util
from google.appengine.ext.webapp import template
from google.appengine.ext import db
from django.utils import simplejson as json
from google.appengine.api import memcache


oauthParams = {
	'key': "BNfyUvvMGkoysLMwT8kCDQ",
	'secret': "tdLUsXAnf7kK2HHb3RI463lmiVTTjWiGwVdXePC54g"
}

class TwitterUser(db.Model):
	accesstoken = db.StringProperty(required = True)
	name = db.StringProperty(required = True)
	username = db.StringProperty(required = True)
	userid = db.StringProperty(required = True)
	avatar = db.StringProperty()
	oauthtoken = db.StringProperty(required = True)
	oauthsecret = db.StringProperty(required = True)
	tweetlist = db.ListProperty(item_type = db.Key)
	last_updated = db.DateTimeProperty(auto_now = True)

class Tweet(db.Model):
	tweetid = db.StringProperty(required = True)
	url = db.StringProperty(required = True)
	tweet = db.TextProperty(required = True)
	pagecontent = db.TextProperty()
	tweetcontent = db.TextProperty()
	tweetdate = db.TextProperty()
	screenname = db.StringProperty()
	username = db.StringProperty()
	useravatar = db.StringProperty()
	processed = db.BooleanProperty(default = False)
	retweetedby_screenname = db.StringProperty()
	retweetedby_username = db.StringProperty()
	retweetedby_useravatar = db.StringProperty()
	retweet = db.BooleanProperty(default = False)

class MainHandler(webapp.RequestHandler):
    def get(self):
		callbackUrl = "%s/verify" % self.request.host_url

		client = oauth.TwitterClient(oauthParams['key'], oauthParams['secret'], callbackUrl)
	
		authorisationUrl = client.get_authorization_url()
	
		templateValues = {
            'authorisationUrl': authorisationUrl
        }

		path = os.path.join(os.path.dirname(__file__), 'index.html')
		self.response.out.write(template.render(path, templateValues))


class VerifyUserHandler(webapp.RequestHandler):
	def get(self):
		callbackUrl = "%s/verify" % self.request.host_url

		#denied = self.request.get("denied")
		
		#if denied != None:
		#	self.redirect('/')

		client = oauth.TwitterClient(oauthParams['key'], oauthParams['secret'], callbackUrl)
		
		authToken = self.request.get("oauth_token")
		authVerifier = self.request.get("oauth_verifier")
		userInfo = client.get_user_info(authToken, authVerifier)
		
		tuser = TwitterUser.gql("WHERE userid = :userid", userid = str(userInfo['id'])).get()
		
		brandnew = False
		
		if tuser == None:
			#accessToken = ''.join(random.choice(string.ascii_uppercase + string.digits) for x in range(45))
			accessToken = hashlib.sha1(str(userInfo['id']) + "," + userInfo['token']).hexdigest()
			
			tuser = TwitterUser(	accesstoken = accessToken,
								name 		= userInfo['name'],
								username 	= userInfo['username'],
			          			userid 		= str(userInfo['id']),
								avatar 		= userInfo['picture'],
								oauthtoken 	= userInfo['token'],
								oauthsecret = userInfo['secret'],
								tweetlist = [])
								
			brandnew = True
		else:
			tuser.name 			= userInfo['name']
			tuser.username 		= userInfo['username']
			tuser.avatar 		= userInfo['picture']
			tuser.oauthtoken 	= userInfo['token']
			tuser.oauthsecret 	= userInfo['secret']
			
		tuser.put()
		
		urlparams = {
			'access': tuser.accesstoken
		}
		
		if brandnew == True:
			urlparams['new'] = 1
		
		taskqueue.add(url = '/parse', params = {'key': tuser.key()} )
		
		self.redirect('/welcome?' + urllib.urlencode(urlparams))
		
		

class WelcomeHandler(webapp.RequestHandler):
	def get(self):
		callbackUrl = "%s/verify" % self.request.host_url
		
		client = oauth.TwitterClient(oauthParams['key'], oauthParams['secret'], callbackUrl)
		
		accessToken = self.request.get("access")
		newUser = self.request.get("new")
		
		if tuser == None:
			tuser = TwitterUser.gql("WHERE accesstoken = :accesstoken", accesstoken = accessToken).get()
		
		if tuser == None:
			return self.error(404)
		
		rssURL = "%s/feed/%s" % (self.request.host_url, accessToken)
		
		tweets = Tweet.get(tuser.tweetlist)
				
		templateValues = {
            'userInfo': tuser,
			'rssURL': rssURL,
			'tweets': tweets,
			'newUser': newUser
        }
		
		path = os.path.join(os.path.dirname(__file__), 'welcome.html')
		self.response.out.write(template.render(path, templateValues))

class LinkDisplayHandler(webapp.RequestHandler):
	def get(self):
		None
				
class LinkRSSHandler(webapp.RequestHandler):
	def get(self, accessToken):

		tuser = TwitterUser.gql("WHERE accesstoken = :accesstoken", accesstoken = accessToken).get()
	
		if tuser == None:
			return self.error(404)

		tweets = Tweet.get(tuser.tweetlist)

		rssURL = "%s/feed/%s" % (self.request.host_url, accessToken)
	
		templateValues = {
            'userInfo': tuser,
			'rssURL': rssURL,
			'tweets': tweets
        }
		
		path = os.path.join(os.path.dirname(__file__), 'feed.html')
	
		renderedFeed = template.render(path, templateValues)
					
		self.response.out.write(renderedFeed)
		
		
class TweetListHandler(webapp.RequestHandler):
	def get(self):
		
		resetTweets = self.request.get("reset")
		
		q = TwitterUser.all(keys_only = False)
		users = q.fetch(30)

		for tuser in users:
			if tuser.avatar is None:
				tuser.avatar = ''
				tuser.put()
			taskqueue.add(url = '/parse', params = {'key': tuser.key()} )
			
	def post(self):
		callbackUrl = "%s/verify" % self.request.host_url
		
		client = oauth.TwitterClient(oauthParams['key'], oauthParams['secret'], callbackUrl)
		
		userKey = self.request.get("key")
		
		tuser = TwitterUser.get(userKey)
		
		timelineParams = {
			'count': 100,
			'include_entities': 1
		}
		
		if len(tuser.tweetlist) > 0:
			lastTweet = Tweet.get(tuser.tweetlist[0])
			
			if lastTweet:
				timelineParams['since_id'] = lastTweet.tweetid
		
		timelineUrl = "http://api.twitter.com/1/statuses/home_timeline.json"
		result = client.make_request(timelineUrl, tuser.oauthtoken, tuser.oauthsecret, timelineParams)
		tweetData = json.loads( result.content )
		
		memcache.add(key = 'temptweets' + tuser.userid, value = tweetData, time = 7200)
		
		taskqueue.add(url = '/parselist', params = {'user': tuser.key(), 'tweetdata': 'temptweets' + tuser.userid, 'start' : 0} )


class TweetListParserHandler(webapp.RequestHandler):
	def post(self):
		userKey = self.request.get("user")
		tweetDataKey = self.request.get("tweetdata")
		start = self.request.get("start")
		newData = self.request.get("newdata")
		
		if start == None:
			start = 0
		
		start = int(start)
		
		if newData == None:
			newData = False
		else:
			newData = True
		
		tuser = TwitterUser.get(userKey)
		tweetData = memcache.get(tweetDataKey)
		
		if tweetData == None:
			memcache.delete(tweetDataKey)
			return
		
		if type( tweetData ) != list:
			memcache.delete(tweetDataKey)
			return
		
		tweetData.reverse()
		tuser.tweetlist.reverse()

		endCount = min(start+5, len(tweetData))	
		
		xcounter = start
		
		for x in range(start, endCount):
			
			xcounter = x
			
			if len(tweetData[x]['entities']['urls']):
				
				newData = True
				
				url = tweetData[x]['entities']['urls'][0]['url']
				
				newTweet = Tweet(
					tweetid = str(tweetData[x]['id']),
					url = url,
					tweet = db.Text(json.dumps(tweetData[x]))
				)
				
				newTweet.put()
				tuser.tweetlist.append(newTweet.key())
				
				taskqueue.add(url = '/parsetweet', params = {'tweetkey': newTweet.key()} )
				
				# changed to a while loop so we can cut down the number of
				# tweets from a higher number
				if len(tuser.tweetlist) > 100:
					while len(tuser.tweetlist) > 100:
						firstKey = tuser.tweetlist.pop(0)
						last = Tweet.get(firstKey)
						if last != None:
							last.delete_async()
		
		
		finished = False
		
		if xcounter >= len(tweetData):
			finished = True
		
		tuser.tweetlist.reverse()		
		tuser.put()
		
		if finished:
			memcache.delete(tweetDataKey)
			
			if newData == True:
				memcache.delete(key = "feedRSS_" + tuser.accesstoken)
				memcache.delete(key = "user_" + tuser.accesstoken)
		
		else:
			taskqueue.add(url = '/parselist', params = {'user': tuser.key(), 'tweetdata': 'temptweets' + tuser.userid, 'start' : start+5, 'newdata' : newData} )
			
		
class TweetDetailsHandler(webapp.RequestHandler):
	def post(self):
		tweetKey = self.request.get("tweetkey")
		
		tweet = Tweet.get(tweetKey)
		
		if tweet == None:
			return
		
		fullTweet = json.loads(tweet.tweet)
		
		if fullTweet.has_key('retweeted_status'):
			tweetcontent = fullTweet['retweeted_status']['text']
			tweet.screenname = fullTweet['retweeted_status']['user']['screen_name']
			tweet.username = fullTweet['retweeted_status']['user']['name']
			tweet.useravatar = fullTweet['retweeted_status']['user']['profile_image_url']
			tweet.tweetdate = datetime.strptime(fullTweet['retweeted_status']['created_at'], '%a %b %d %H:%M:%S +0000 %Y').strftime('%a, %d %b %Y %H:%M:%S +0000')
			tweet.retweetedby_screenname = fullTweet['user']['screen_name']
			tweet.retweetedby_username = fullTweet['user']['name']
			tweet.retweetedby_useravatar = fullTweet['user']['profile_image_url']
			tweet.retweet = True
		else:
			tweetcontent = fullTweet['text']
			tweet.screenname = fullTweet['user']['screen_name']
			tweet.username = fullTweet['user']['name']
			tweet.useravatar = fullTweet['user']['profile_image_url']
			tweet.tweetdate = datetime.strptime(fullTweet['created_at'], '%a %b %d %H:%M:%S +0000 %Y').strftime('%a, %d %b %Y %H:%M:%S +0000')
			
		for url in fullTweet['entities']['urls']:
			tweetcontent = tweetcontent.replace(url['url'], '<a href="'+url['url']+'">'+url['url']+'</a>')
			
		for mentions in fullTweet['entities']['user_mentions']:
			tweetcontent = tweetcontent.replace('@' + mentions['screen_name'], '<a href="http://twitter.com/'+mentions['screen_name']+'">@'+mentions['screen_name']+'</a>')
			
		for hashtags in fullTweet['entities']['hashtags']:
			tweetcontent = tweetcontent.replace('#' + hashtags['text'], '<a href="http://search.twitter.com/search?q=%23'+hashtags['text']+'">#'+hashtags['text']+'</a>')
			
		tweet.tweetcontent = tweetcontent
			
		tweet.processed = True
		
		tweet.put()
		

application = webapp.WSGIApplication([	('/', MainHandler),
										('/verify', VerifyUserHandler),
										('/welcome', WelcomeHandler),
										('/links', LinkDisplayHandler),
										('/feed/([^\/]*?)/?', LinkRSSHandler),
										('/parse', TweetListHandler),
										('/parselist', TweetListParserHandler),
										('/parsetweet', TweetDetailsHandler)],
                                         debug=True)

def real_main():
    util.run_wsgi_app(application)

def profile_main():
    # This is the main function for profiling
    # We've renamed our original main() above to real_main()
    import cProfile, pstats, StringIO
    prof = cProfile.Profile()
    prof = prof.runctx("real_main()", globals(), locals())
    stream = StringIO.StringIO()
    stats = pstats.Stats(prof, stream=stream)
    stats.sort_stats("time")  # Or cumulative
    stats.print_stats(80)  # 80 = how many to print
    # The rest is optional.
    # stats.print_callees()
    # stats.print_callers()
    logging.info("Profile data:\n%s", stream.getvalue())

main = profile_main

if __name__ == '__main__':
    main()