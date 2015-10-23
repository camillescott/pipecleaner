import pandas as pd
import time

from evelink.map import Map
from flask import Flask, render_template, redirect, url_for
app = Flask(__name__)

class EveData(object):
    '''Manages EVE API access.

    Queries the EVE API for kills, jumps, and sovereignty. Stores
    history in a Pandas panel and writes it to disk on occasion (JK not yet
    actually, but soon (tm)).

    Attributes:
        systems_df (DataFrame): Data for the nullsec entry systems.
        system_ids (Series): Series with all relevant system IDs, for
        convenience.
        last_query_time (Timestamp): Most recent successful query to the API.
        map_api (Map): The evelink Map API object.
    '''

    update_interval = 1200
    retry = 5
    max_frames = 100
    keys = ['Dest_ID', 'Entry_ID', 'Dest', 'Dest_Region', 
            'Dest_TrueSec', 'Entry', 'Entry_Region', 'Entry_Sec', 
            'Entry_ShipKills', 'Entry_PodKills', 'Entry_Jumps', 
            'Dest_ShipKills', 'Dest_PodKills', 'Dest_Jumps']

    def __init__(self, data_fn='data/systems.json'):
        '''Initialize a new EveData object.

        Queries the API for system data on creation.

        Args:
            data_fn (str): Path to JSON file with subset of systems.
        '''

        self.systems_df = pd.read_json(data_fn)
        self.system_ids = set(pd.concat([self.systems_df.Entry_ID, 
                                     self.systems_df.Dest_ID]))

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
        '''Perform a query for jumps, kills, and sov against the EVE API.

        Notes:
            Raises an exception when the query fails, and does *not* update
            the last_query_time attribute.
        Returns:
            (DataFrame, DataFrame, DataFrame): DataFrames with kills, jumps and
            sov, respectively.
        '''

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
        '''Get the most recent API data being stored.

        Returns:
            (Timestamp, DataFrame): Last update time and the merged result DataFrame.
        '''

        kills = self.kills_history[self.last_query_time]
        jumps = self.jumps_history[self.last_query_time]

        merged = self.systems_df.copy()
        merged = merged.set_index('Entry_ID').sort_index()
        merged['Entry_ShipKills'] = kills.ix[self.systems_df.Entry_ID].ship.sort_index()
        merged['Entry_PodKills'] = kills.ix[self.systems_df.Entry_ID].pod.sort_index()
        merged['Entry_Jumps'] = jumps.ix[self.systems_df.Entry_ID].jumps.sort_index()
        merged.reset_index(inplace=True)

        merged = merged.set_index('Dest_ID').sort_index()
        merged['Dest_ShipKills'] = kills.ix[self.systems_df.Dest_ID].ship.sort_index()
        merged['Dest_PodKills'] = kills.ix[self.systems_df.Dest_ID].pod.sort_index()
        merged['Dest_Jumps'] = jumps.ix[self.systems_df.Dest_ID].jumps.sort_index()
        merged.reset_index(inplace=True)

        merged.sort_values('Dest_Region', inplace=True)
        merged.fillna(0, inplace=True)

        return self.last_query_time, merged


    def update(self):
        '''Update the API if its been more than 20 minutes since the last query.

        Returns the most recent data, regardless of whether the update succeeds.

        Returns:
            The latest data (see the latest() method)
        '''

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

                if len(self.kills_history) >= EveData.max_frames:
                    del self.kills_history[self.kills_history.index.min()]
                if len(self.jumps_history) >= EveData.max_frames:
                    del self.jumps_history[self.jumps_history.index.min()]
                if len(self.kills_history) >= EveData.max_frames:
                    del self.sov_history[self.sov_history.index.min()]

        return self.latest()

    def dump(self):
        pass

data = EveData()


@app.route('/')
@app.route('/groupby/Region')
def region():
    timestamp, results_df = data.update()

    return render_template('groupby_region.html', 
                           timestamp=timestamp,
                           results_df=results_df)

@app.route('/sortby/<key>')
def sortby(key):
    if key not in EveData.keys:
        return redirect(url_for('region'))

    timestamp, results_df = data.update()
    

    results_df.sort_values(key, inplace=True)
    return render_template('sortby.html',
                           timestamp=timestamp,
                           results_df=results_df)

if __name__ == '__main__':
    app.run(debug=True)
