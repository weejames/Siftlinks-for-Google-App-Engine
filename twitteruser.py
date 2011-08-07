#!/usr/bin/env python

from google.appengine.ext import db

class TwitterUser(db.Model):
	accesstoken = db.StringProperty(required = True)
	name = db.StringProperty(required = True)
	username = db.StringProperty(required = True)
	userid = db.StringProperty(required = True)
	avatar = db.StringProperty(required = True)
	oauthtoken = db.StringProperty(required = True)
	oauthsecret = db.StringProperty(required = True)