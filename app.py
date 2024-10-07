import os
from flask import Flask, request, jsonify, render_template, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from textblob import TextBlob
import json
from datetime import datetime
import tweepy
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file

TWITTER_API_KEY = os.getenv('TWITTER_API_KEY')
TWITTER_API_SECRET = os.getenv('TWITTER_API_SECRET')
TWITTER_ACCESS_TOKEN = os.getenv('TWITTER_ACCESS_TOKEN')
TWITTER_ACCESS_TOKEN_SECRET = os.getenv('TWITTER_ACCESS_TOKEN_SECRET')

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///sentiment_dashboard.db'
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    searches = db.relationship('Search', backref='user', lazy='dynamic')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Search(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    query = db.Column(db.String(128), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    results = db.relationship('Result', backref='search', lazy='dynamic')

class Result(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.String(280))
    sentiment = db.Column(db.Float)
    search_id = db.Column(db.Integer, db.ForeignKey('search.id'))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def analyze_sentiment(text):
    analysis = TextBlob(text)
    return analysis.sentiment.polarity

def fetch_tweets(query):
    auth = tweepy.OAuthHandler(TWITTER_API_KEY, TWITTER_API_SECRET)
    auth.set_access_token(TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET)
    api = tweepy.API(auth)

    tweets = []
    for tweet in tweepy.Cursor(api.search_tweets, q=query, tweet_mode='extended').items(100):
        tweets.append({
            'text': tweet.full_text,
            'user': tweet.user.screen_name,
            'created_at': tweet.created_at,
            'retweet_count': tweet.retweet_count,
            'favorite_count': tweet.favorite_count
        })
    
    return tweets


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
@login_required
def analyze():
    query = request.form['query']
    tweets = fetch_tweets(query)
    
    search = Search(query=query, user=current_user)
    db.session.add(search)
    
    results = []
    for tweet in tweets:
        sentiment = analyze_sentiment(tweet['text'])
        result = Result(
            text=tweet['text'], 
            sentiment=sentiment, 
            search=search,
            user=tweet['user'],
            created_at=tweet['created_at'],
            retweet_count=tweet['retweet_count'],
            favorite_count=tweet['favorite_count']
        )
        db.session.add(result)
        results.append({
            'text': tweet['text'], 
            'sentiment': sentiment,
            'user': tweet['user'],
            'created_at': tweet['created_at'],
            'retweet_count': tweet['retweet_count'],
            'favorite_count': tweet['favorite_count']
        })
    
    db.session.commit()
    
    return jsonify(results)

@app.route('/history')
@login_required
def history():
    searches = current_user.searches.order_by(Search.timestamp.desc()).all()
    return render_template('history.html', searches=searches)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and user.check_password(request.form['password']):
            login_user(user)
            return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        user = User(username=request.form['username'])
        user.set_password(request.form['password'])
        db.session.add(user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('register.html')

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)