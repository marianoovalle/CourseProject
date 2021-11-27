import re
from dataclasses import dataclass

import demoji
import tweepy


@dataclass
class Tweet:
    text: str = ""
    likes_count: int = 0
    retweets_count: int = 0
    followers_count: int = 0
    sentiment_score: float = 0.0


class TwitterClient:
    def __init__(self, consumer_key="xlinnUvFlgoU2JQlynXU5Vx14",
                 consumer_secret="36Pdrs0qNMqYUg8DBbVBRAiSC4i5yNb27Xo6Tm9XGg5JlNpBeT"):
        auth = tweepy.AppAuthHandler(consumer_key, consumer_secret)
        self.api = tweepy.API(auth)

    def get_tweets(self, symbol, name="", industry="", allow_duplicates=False, tweets_limit=500):
        all_tweets = self.__query(f"${symbol}", tweets_limit)
        tweets = []
        if not allow_duplicates:
            text_list = []
            for tweet in all_tweets:
                if tweet.text not in text_list:
                    text_list.append(tweet.text)
                    tweets.append(tweet)
        else:
            tweets = all_tweets
        return tweets

    def __preprocess(self, raw_tweet):
        # Remove emojis
        demoji_str = demoji.replace(raw_tweet.full_text, "").strip().replace("\n", " ")

        # Remove user names
        demoji_str = re.sub(r'RT @\w+: ?', '', demoji_str)
        demoji_str = re.sub(r'@\w+ ?', '', demoji_str)

        # Remove hashtags
        demoji_str = re.sub(r'#\w+ ?', '', demoji_str)

        # Remove http urls
        demoji_str = re.sub(r'http\S+', '', demoji_str)

        tweet = Tweet()
        tweet.text = demoji_str
        tweet.likes_count = raw_tweet.favorite_count
        tweet.retweet_count = raw_tweet.retweet_count
        tweet.followers_count = raw_tweet.user.followers_count
        return tweet

    def __query(self, search_query, tweets_limit=50):
        raw_tweets = tweepy.Cursor(self.api.search_tweets,
                                   q=search_query, lang="en",
                                   tweet_mode='extended').items(tweets_limit)
        processed_tweets = [self.__preprocess(rt) for rt in raw_tweets]
        return processed_tweets

    def save(self, tweets, filename):
        if filename:
            with open(filename, "w") as sfile:
                sfile.write("\n".join([tweet.text for tweet in tweets]))


if __name__ == "__main__":
    twitter_client = TwitterClient()
    loaded_tweets = twitter_client.get_tweets("$amzn", allow_duplicates=False, tweets_limit=50)
    # print(loaded_tweets)
    # twitter_client.save(loaded_tweets, "tweets.txt")
