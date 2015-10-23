import pandas as pd
import time

from evelink.map import Map
from flask import Flask, render_template
app = Flask(__name__)

class EveData(object):

    update_interval = 1200
    retry = 5

    def __init__(self, data_fn='data/systems.json'):
        self.systems_df = pd.read_json(data_fn)
        self.system_ids = pd.concat([self.systems_df.Entry_ID, 
                                     self.systems_df.Dest_ID])

        self.last_query_time = None
        self.map_api = Map()
        
        tries = 0
        while(self.last_query_time is None):
            try:
                kills_df, jumps_df, sov_df = self.query()
            except Exception as e:
                print 'Error querying API on __init__:', e
                print 'Retrying [tries: {0}]'.format(tries)
                tries += 1

            else:
                self.kills_history = pd.Panel({self.last_query_time: kills_df})
                self.jumps_history = pd.Panel({self.last_query_time: jumps_df})
                self.sov_history = pd.Panel({self.last_query_time: sov_df})
            finally:
                if tries >= EveData.retry:
                    raise RuntimeError('Failed to query API on __init__')

    def query(self):

        try:
            kills_res, _ = self.map_api.kills_by_system().result
            jumps_res, _ = self.map_api.jumps_by_system().result
            sov_res, _ = self.map_api.sov_by_system().result
        except Exception as e:
            print 'Error querying API:', e
            raise
        else:
            self.last_query_time = pd.Timestamp(time.ctime())

            kills_df = pd.DataFrame(kills_res).T.ix[self.system_ids]
            jumps_df = pd.DataFrame({'jumps': pd.Series(jumps_res)}).ix[self.system_ids]
            sov_df = pd.DataFrame(sov_res).T.ix[self.system_ids]

            return kills_df, jumps_df, sov_df

    def latest(self):
        return self.last_query_time, \
               self.kills_history[self.last_query_time], \
               self.jumps_history[self.last_query_time], \
               self.sov_history[self.last_query_time]


    def update(self):
        cur_time = pd.Timestamp(time.ctime())
        if (cur_time - self.last_query_time).seconds > EveData.update_interval:
            try:
                kills_df, jumps_df, sov_df = self.query()
            except:
                pass
            else:
                self.kills_history[self.last_query_time] = kills_df
                self.jumps_history[self.last_query_time] = jumps_df
                self.sov_history[self.last_query_time] = sov_df
        return self.latest()

data = EveData()

@app.route('/')
def home():
    timestamp, kills, jumps, sov = data.update()
    print timestamp
    print kills.head()
    print data.systems_df.head()
    return render_template('main.html', timestamp=timestamp,
                                        systems=data.systems_df,
                                        kills=kills,
                                        jumps=jumps)

if __name__ == '__main__':
    app.debug = True
    app.run()
