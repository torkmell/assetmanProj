# Random Forest model for stocks
# MSc Finance ESADE June 2021


import pandas as pd
import numpy as np 
#import rle1
#import RLE
from datetime import datetime
from dateutil.relativedelta import relativedelta
import os
import io
import itertools
import time
from urllib.parse import urlencode
from functools import reduce
import matplotlib.pyplot as plt
import ta
import scipy as sp
from tabulate import tabulate
pd.options.display.max_columns = None
pd.options.display.width=None

#import pandas_datareader.data as web
import pandas_datareader as web
import seaborn as sns


# *** for Bayesian optimization


from sklearn.model_selection import cross_val_score, train_test_split, GridSearchCV, RandomizedSearchCV
from sklearn import datasets, pipeline
import lightgbm as lgb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import random
import seaborn as sns
import time
%matplotlib qt

import warnings

warnings.filterwarnings('ignore')
warnings.filterwarnings(action='ignore',category=DeprecationWarning)
warnings.filterwarnings(action='ignore',category=FutureWarning)

# *** For hierarchical risk parity
import pypfopt

from pypfopt import EfficientFrontier
from pypfopt import risk_models
from pypfopt import expected_returns
from pypfopt import hierarchical_portfolio
from pypfopt import HRPOpt


# ***
os.chdir('C:/Users/joses/Dropbox/My PC (LAPTOP-7NM3B9C6)/Desktop/ESADE/Asset Management/SESSIONS/6_Machine_Learning/Random Forest')

prices = pd.read_csv("monthly_div.csv")

cols = list(prices.columns)[2:]

prices_for_hrp = pd.read_csv("monthly_div.csv")

# ***************************************************
# GLOBAL PARAMETERS
max_n_data_rep = 5
max_mreturn = 1
target_return = 0.01

# ***************************************************


def years_of_data(df, col, n_required = 7, frequency = "m"):
    """
    minimum number of years of history that we require from a stock
    """
    if frequency == "m":
        year = 12
    elif frequency == "q":
        year = 4
    else:
        raise ValueError("frequency must be either m or q")
    if df[col].isna().count() - df[col].isna().sum() <= n_required*year:
        df = df.drop(col, axis=1)
    return df

#apply years filter to the prices data
for col in cols:
    prices = years_of_data(prices, col)

def encode(sequence):
    """Encode a sequence of characters and return the result as a list of tuples (data value and number of observed instances of value).
    Keyword arguments:
    sequence -- a sequence of characters to encode represented as a string.
    """
    count = 1
    result = []

    for x,item in enumerate(sequence): 
        if x == 0:
            continue
        elif item == sequence[x - 1]:
            count += 1
        else:        
            result.append((sequence[x - 1], count))
            count = 1            
    
    result.append((sequence[len(sequence) - 1], count))

    return result


def drop_consecutive_duplicates(df, col, n_allowed = 5):
    """
    drop a column if there are more than a certain number of 
    consecutive repeated data
    """
    x = n_allowed
    mylist = []
    for i in range(len(encode(df[col].values))):
      n = encode(df[col].values)[i][1]
      mylist.append(n)
    if any(y >= x for y in mylist):
        df = df.drop(col, axis = 1)
    return df

#apply the duplicates filter to prices
#for col in prices.columns:
#    prices = drop_consecutive_duplicates(prices, col)

###############################################################
# Alternative attempt (Jose)  

max_dupl_list = []
col_names = list(prices.columns)[2:]

for n in col_names:
    dupl_tuple = [(x[0], len(list(x[1]))) for x in itertools.groupby(prices[n])]
    dupl_tuple_max = max(dupl_tuple, key=lambda x:x[1])[1]
    
    max_dupl_list.append(dupl_tuple_max)

# inserting 2 columns at the beginning of the list so that their number match the number of
    # columns in PRICES

max_dupl_list.insert(0, 'mtime')
max_dupl_list.insert(1, 'date')

max_dupl_list_df = pd.DataFrame(max_dupl_list)
max_dupl_list_df = max_dupl_list_df.T
max_dupl_list_df.columns = prices.columns
for col in col_names:
    max_dupl_list_df[col] = pd.to_numeric(max_dupl_list_df[col])
 
names_data_norep = list(max_dupl_list_df.iloc[:,2:].columns[(max_dupl_list_df.iloc[:,2:] <= max_n_data_rep).iloc[0]])
names_data_norep.insert(0, 'mtime')
names_data_norep.insert(1, 'date')

prices = prices[prices.columns.intersection(names_data_norep)]


###############################################################
 

col_names1 = list(prices.columns)[2:]


returns = prices.iloc[:, 2:].pct_change()

#drop columns where returns are > 130%
returns_max = pd.DataFrame(
        returns[n].max() for n in col_names1 # calculate returns across columns
        )

returns_max = returns_max.T
returns_max.columns = col_names1

names_max_mreturn = list(returns_max.columns[(returns_max <= max_mreturn).iloc[0]])
names_max_mreturn.insert(0, 'mtime')
names_max_mreturn.insert(1, 'date')

prices = prices[prices.columns.intersection(names_max_mreturn)]

to_keep = prices.columns


# *******************************************************************************
# TECHNICAL INDICATORS
  
def get_EMA(period, col, data):
    """
    get the Exponential Moving Average
    """
    EMA = data[col].ewm(span= period).mean()
    return EMA

def get_MA(period, col, data):
    """
    get the Simple Moving Average
    """
    MA = data[col].rolling(period).mean()
    return MA

def get_MACD(EMA1, EMA2, col):
    """
    get the MACD
    """
    MACD = EMA2[col]-EMA1[col]
    return MACD

def bb_u(period, col, data):
    """
    calculates bollinger bands
    """
    rolling_mean = data[col].rolling(period).mean()
    ub = rolling_mean + 2*data[col].rolling(period).std()
    ub_signal = ub - data[col]
    return ub_signal

def bb_l(period, col, data):
    """
    calculates bollinger bands
    """
    rolling_mean = data[col].rolling(period).mean()
    lb = rolling_mean - 2*data[col].rolling(period).std()
    lb_signal = data[col] - lb
    return lb_signal

def relative_strength(period, col, data):
    """
    calculates relative strength index
    """
    move = data[col]-data[col].shift(1)
    move_g0 = np.where(move>0,move,0)
    move_l0 = np.where(move<0,move,0)

    gain_av = pd.DataFrame(move_g0).rolling(period).mean()
    loss_av = -(pd.DataFrame(move_l0).rolling(period).mean())
    rsi = (100 - (100/(1+(gain_av/loss_av))))
   # rsi = (100 - (100/(1+(gain_av.div(loss_av.values,axis=0)))))
    return rsi

#create a SMA DataFrame
SMA = []
for col in prices.columns[2:]:
    SMA.append(get_MA(3, col, prices))
SMA = pd.DataFrame(SMA).transpose()  

#create an EMA DataFrame
EMA = []
for col in prices.columns[2:]:
    EMA.append(get_EMA(3, col, prices))
EMA = pd.DataFrame(EMA).transpose() 

#create a MACD DataFrame
MACD = []
for col in prices.columns[2:]:
    MACD.append(get_MACD(prices, SMA, col))
MACD = pd.DataFrame(MACD).transpose()

#get the standard deviation of the stocks
STD = []
for col in prices.columns[2:]:
    STD.append(returns[col].rolling(window = 12).std())
STD = pd.DataFrame(STD).transpose() 



RSI = []
for col in prices.columns[2:]:
    #RSI.append(relative_strength(12,col,prices))
    RSI.append(ta.momentum.rsi(close=prices[col],window=6)) # taking the function from 'ta' package
RSI = pd.DataFrame(RSI).transpose() 
RSI.columns = MACD.columns

ROC2 = [] # 2 month roc
ROC3 = [] # 3 month roc
for col in prices.columns[2:]:
    ROC2.append(ta.momentum.roc(close=prices[col],window=2)) # taking the function from 'ta' package
    ROC3.append(ta.momentum.roc(close=prices[col],window=3)) # taking the function from 'ta' package

ROC2 = pd.DataFrame(ROC2).transpose() 
ROC2.columns = MACD.columns
ROC3 = pd.DataFrame(ROC3).transpose() 
ROC3.columns = MACD.columns

TSI = []
STOCH = []
WR = []
DC = []
KC = []
ATR = []
BB = []
#AI = []
CCI = []
DPO = []
for col in prices.columns[2:]:
    TSI.append(ta.momentum.tsi(close=prices[col],window_slow=6,window_fast=3)) # taking the function from 'ta' package
    WR.append(ta.momentum.williams_r(high=prices[col],low=prices[col],close=prices[col],lbp=6)) # taking the function from 'ta' package
    DC.append(ta.volatility.donchian_channel_pband(high=prices[col],low=prices[col],close=prices[col],window=6)) # taking the function from 'ta' package
    ATR.append(ta.volatility.average_true_range(high=prices[col],low=prices[col],close=prices[col],window=6)) # taking the function from 'ta' package
    BB.append(ta.volatility.bollinger_pband(close=prices[col],window=6, window_dev=2)) # taking the function from 'ta' package

TSI = pd.DataFrame(TSI).transpose() 
TSI.columns = MACD.columns
WR = pd.DataFrame(WR).transpose() 
WR.columns = MACD.columns
DC = pd.DataFrame(DC).transpose() 
DC.columns = MACD.columns
ATR = pd.DataFrame(ATR).transpose() 
ATR.columns = MACD.columns
BB = pd.DataFrame(BB).transpose() 
BB.columns = MACD.columns



#combine the 'prices', 'returns', 'SMA', 'EMA', 'MACD' DataFrames in a dictionary of DataFrames
# comnining on the keys (eg. "A")
price_merged = {idx: gp.droplevel(1, axis=1) for idx, gp in 
                    pd.concat([returns, SMA, EMA, MACD, RSI, ROC2, ROC3, TSI, WR, DC, ATR, BB],
                              keys=['returns', 'SMA', 'EMA', 'MACD', 'RSI', 'ROC2', 'ROC3', 'TSI', 'WR', 'DC', 'ATR', 'BB'],
                              axis=1).groupby(level=1, axis=1)}


debtequity = pd.read_csv("us_debtequity.csv")
fcf = pd.read_csv("us_fcf.csv")
per = pd.read_csv("us_per.csv")
volume = pd.read_csv("us_volume.csv")

var_list = [debtequity, fcf, per, volume]

#dropping all the columns that had already been dropped in the prices
for i in range(len(var_list)):
    var_list[i] = var_list[i][to_keep]
    
debtequity, fcf, per, volume = var_list

#dividing the dataframes by their frequency
quarterly =  [debtequity, fcf]
monthly = [per, volume]

#applying the years filter on the quarterly data
for i in range(len(quarterly)):
    for col in to_keep:
        quarterly[i] = years_of_data(quarterly[i], col, frequency = "q")
            
#applying the years filter on the monthly data
for i in range(len(monthly)):
    for col in to_keep:
        monthly[i] = years_of_data(monthly[i], col)
            
#assign the variables again
debtequity, fcf = quarterly
per, volume = monthly

# if the repetition is in the last 4/12 spots (1 year) we don't drop the columns
def duplicates_cut(df, num, n_allowed = 5):
    """
    drop consecutive duplicates in a dataframe, excluding a certain number of rows at the end
    """
    df_cut = df[: - num]
    for col in df_cut.columns:
        df_cut = drop_consecutive_duplicates(df_cut, col, n_allowed = n_allowed)
    keepers = df_cut.columns
    return df[keepers]


################################################################################################
    
def drop_rle_duplicates(df, last_obs, max_n_data_rep):
    """
    Calculates Running Length duplicates and drops columns of a dataframe, df, containing more duplicates than max_n_data_rep
    !!! applies to df with mtime and date on first 2 columns
    """
    max_dupl_list = []
    col_names = list(df.columns)[2:]
    df_truncated = df[: -last_obs]
    
    for n in col_names:
        dupl_tuple = [(x[0], len(list(x[1]))) for x in itertools.groupby(df_truncated[n])]
        dupl_tuple_max = max(dupl_tuple, key=lambda x:x[1])[1]
    
        max_dupl_list.append(dupl_tuple_max)

    # inserting 2 columns at the beginning of the list so that their number match the number of
        # columns in PRICES

    max_dupl_list.insert(0, 'mtime')
    max_dupl_list.insert(1, 'date')

    max_dupl_list_df = pd.DataFrame(max_dupl_list)
    max_dupl_list_df = max_dupl_list_df.T
    max_dupl_list_df.columns = df.columns
    for col in col_names:
        max_dupl_list_df[col] = pd.to_numeric(max_dupl_list_df[col])
 
    names_data_norep = list(max_dupl_list_df.iloc[:,2:].columns[(max_dupl_list_df.iloc[:,2:] <= max_n_data_rep).iloc[0]])
    names_data_norep.insert(0, 'mtime')
    names_data_norep.insert(1, 'date')

    df = df[df.columns.intersection(names_data_norep)]
    
    return df


##############################################################################################
    
for i in range(len(quarterly)):
    quarterly[i] = drop_rle_duplicates(quarterly[i],4,max_n_data_rep)
    
    
#apply the duplicates filter to monthly data
for i in range(len(monthly)):
    monthly[i] = drop_rle_duplicates(monthly[i],12,max_n_data_rep=12)


#assing the variables again
debtequity, fcf = quarterly
per, volume = monthly

def replace_null(df):
    """
    replace the NaN Values in the middle and at the end
    Middle: average of last available value and next available
    End: last available value
    """
    df = df.where(df.notnull(), other=(df.fillna(method='ffill')+df.fillna(method='bfill'))/2)
    if df[len(df)//2 :].isna().any().any() == True:
        df[len(df)//2 :] = df[len(df)//2 :].fillna(method = "ffill")
    return df

var_list = [debtequity, fcf, per, volume]

#replace the null values for all the  numerical variblees in varlist 
for i in range(len(var_list)):
    var_list[i].iloc[:, 2:] = replace_null(var_list[i].iloc[:, 2:])
    
#assing all the variables again
debtequity, fcf, per, volume = var_list

#save the values as csv files
index_val = ["debtequity", "fcf", "per", "volume"]

for i in range(len(var_list)):
    var_list[i].to_csv(f"{index_val[i]}.csv", index = False)
    

# ++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

#combine the DataFrames with quarterly frequency in a dictionary 
#of DataFrames, combining on the keys (eg. "A")
quarterly_merged = {idx: gp.droplevel(1, axis=1) for idx, gp in
                  pd.concat([debtequity, fcf],\
                            keys=['debtequity','fcf'], \
                            axis=1).groupby(level=1, axis=1)}

#combine the DataFrames with monthly frequency in a dictionary 
#of DataFrames, combining on the keys (eg. "A")
monthly_merged = {idx: gp.droplevel(1, axis=1) for idx, gp in 
                    pd.concat([per, volume],  
                              keys=['per','volume'],        
                              axis=1).groupby(level=1, axis=1)}

        

#for only the variables that are present in prices, merge it with the monthly and quarterly data, for quarterly, fill the NaN with the last available
start = time.time()
for key in price_merged.keys():
    if key in monthly_merged.keys():
        if key in quarterly_merged.keys():
            globals()[f'{key}'] = (pd.concat([prices[["mtime", "date"]], price_merged[key], \
                                          monthly_merged[key]], axis = 1)).merge(pd.concat\
                                                                                 ([debtequity[["mtime", "date"]], \
                                                                                   quarterly_merged[key]], axis = 1), \
                                                                                 how = "left", on = ["mtime"]\
                                                                                ).drop("date_y", axis = 1 \
                                                                                      ).fillna(method = "ffill")
        else:
            globals()[f'{key}'] = (pd.concat([prices[["mtime", "date"]], price_merged[key], \
                                          monthly_merged[key]], axis = 1))
    else:
        if key in quarterly_merged.keys():
            globals()[f'{key}'] = pd.concat([prices[["mtime", "date"]], price_merged[key]], axis = 1).merge(pd.concat\
                                                                                 ([debtequity[["mtime", "date"]], \
                                                                                   quarterly_merged[key]], axis = 1), \
                                                                                 how = "left", on = ["mtime"]\
                                                                                ).drop("date_y", axis = 1 \
                                                                                      ).fillna(method = "ffill")
        else:
            globals()[f'{key}'] = pd.concat([prices[["mtime", "date"]], price_merged[key]], axis = 1)
            
end = time.time()
print(end - start)


   
# &&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&
# --------------------------------------------------------------------------------------------------------

# *** RANDOM FOREST MODELS


from sklearn.model_selection import  train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score
from sklearn.model_selection import RandomizedSearchCV

# function to single out the last row azvailable of data
def get_last(data):
    last = data[-1:].drop("target", axis = 1)
    return last

# function to split the data
def split_data_seq(data, target, test_size = 0.2):
    last = get_last(data)
    data.dropna(inplace = True)
    X = data.drop(target, axis = 1)
    y = data[target]
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=test_size, random_state=42)
    return X_train, X_test, y_train, y_test, last

#function to predict if the next month return will be above 2%
def predict_next(model, last):
    prob = model.predict_proba(last)
    pred = model.predict(last)
    return pred, prob

#function to run the rf using data, get predictions , probability and accuracy

def run_rf(model, data, target, test_size = 0.2):
    """
    handle the data and run it in the model
    """
    X_train, X_test, y_train, y_test, last = split_data_seq(data, target, test_size = test_size)
    model.fit(X_train, y_train)
    pred = model.predict(X_test)
    prob = model.predict_proba(X_test)
    acc = accuracy_score(y_test, pred)
    last_pred, last_proba = predict_next(model, last)
    return pred, prob, acc, last_pred, last_proba


#define the target 
for key in price_merged.keys():
    globals()[f'{key}']["target"] = 0
    

# *** This code is to delete companies (DF inside the dictionary price_merged) that dont have returns
    # you get the error 'RunTimeError dictionary changed during iteration' but can be ignored
    # however we introduce the following to avoid modifying the dictionary
import copy
price_merged_copy = copy.deepcopy(price_merged)

for key in price_merged.keys():
    if 'returns' not in globals()[f'{key}'].columns:
        del price_merged_copy[key]

price_merged = price_merged_copy
# ********************************************************


#define the target and shift
for key in price_merged.keys():
    for i in range((len(globals()[f'{key}']["returns"]))): 
        if globals()[f'{key}']["returns"][i] >= target_return:
            globals()[f'{key}']["target"][i] = 1
            #globals()[f'{key}'].loc[i,"target"] = 1
    globals()[f'{key}']["target"] = globals()[f'{key}']["target"].shift(-1)
    
#fix the different date names
mapper = {"date_x": "date"}
for key in price_merged.keys():
    globals()[f'{key}'].rename(mapper, axis = 1, inplace = True)  
    globals()[f'{key}'].drop("mtime", axis=1, inplace = True) 
    globals()[f'{key}']['date'] = pd.to_datetime(globals()[f'{key}']['date']).dt.to_period('M').dt.to_timestamp()


# *****************************
# GET THE MACRO DATA
  
macro = pd.read_csv('macro_data.csv')
macro['date'] = pd.to_datetime(macro['date']).dt.to_period('M').dt.to_timestamp()

macro = macro.drop("mtime", axis=1)

#merge all with the macro dataset
for key in price_merged.keys():
    globals()[f"{key}"] = globals()[f"{key}"].merge(macro, how = "left", on = "date")


#set "date" as index so it's not taken into consideration
for key in price_merged.keys():
    globals()[f'{key}'].set_index("date", inplace = True)
    
    
    
    
    
# *** # *** # //////////////////////////////////////////////////////////////////////////////////
    # UP TO HERE DATA CLEANING AND MANIPULATION
    
    # MODEL BUILDING STARTS HERE
   
# INITIAL PLAN    
# choose the best parameters 
# run rf with best parameters for most accurate companies, find next month prediction
# find at each point in time the best companies
# optimal calibration for those companies
# consider only companies with a certain ammount of data
# consider only the 20 most accurate companies
# predict next month 
# equal weight portfolio
# compute return 
# (do it for last 12 months)


# Check if the target variable is imbalanced

df_imbalance = {}
for key in price_merged.keys():
    df_imbalance[key] = globals()[f'{key}']["target"].mean()
    
# mean of all companies
from statistics import mean
df_imbalance_mean = mean([df_imbalance[k] for k in df_imbalance])

# plot hist
plt.bar(df_imbalance.values(), df_imbalance.values(), width=1, color='g')
a = list(df_imbalance.values())
plt.hist(a)

# define the model

# HYPERPARAMETER TUNING ****************************************************
# Number of trees in random forest
n_estimators = [int(x) for x in np.linspace(start = 30, stop = 80, num = 10)]

# Maximum number of levels in tree
max_depth = [int(x) for x in np.linspace(5, 70, num = 10)]
max_depth.append(None)
# Minimum number of samples required to split a node
min_samples_split = [4, 6, 8]
# Minimum number of samples required at each leaf node
min_samples_leaf = [1, 2, 3]
# Method of selecting samples for training each tree
bootstrap = [True, False]
# Create the random grid
random_grid = {'n_estimators': n_estimators,
#               'max_features': max_features,
               'max_depth': max_depth,
               'min_samples_split': min_samples_split,
               'min_samples_leaf': min_samples_leaf,
               'bootstrap': bootstrap}



not_allowed = set([0.0, np.nan])

for key in price_merged.keys():
    globals()[f'{key}'] = globals()[f'{key}'].dropna(axis=1, how='all') # droping columns with all NaN to avoid empty sets when dropping NaN by rows at next step
    globals()[f'{key}'] = globals()[f'{key}'].loc[:,~(globals()[f'{key}'].isin(not_allowed).all()==True)]  # dropping columns containing some 0s and NaNs

# *****************************************************************************
#   GRID SEARCH & RANDOM SEARCH
    
    
# Random search of parameters, using 3 fold cross validation, 
# search across 100 different combinations, and use all available cores
#test_size = 0.2

#X = data.drop(target, axis = 1)
#y = data[target]

accuracy = {} # Initialize a list/dictionary to store the accuracy #s for each company
last_month = {}  # Initialize a list/dictionary to store the data for the month to be forecast by the final model
rf_parameters = {}
forecast = {}
forecast_prob = {}
predicted_prob = {}

# removing empty data frames in the dictionary
#new_frames = {k:v for (k,v) in frames.items() if v != []}

for key in price_merged.keys():
    globals()[f'{key}'] = globals()[f'{key}'].dropna(axis=1, how='all') # droping columns with all NaN to avoid empty sets when dropping NaN by rows at next step

test_size = 0.2

d1 = list(price_merged.keys())[0:25]

#for key in price_merged.keys():
for key in d1:
    print('Model for '+str(key))
    last_month[key] = globals()[f'{key}'][-1:].drop("target", axis = 1)
    globals()[f'{key}'] = globals()[f'{key}'][:-1]  # drop last observation NaN on 'target'
    globals()[f'{key}'] = globals()[f'{key}'].dropna(axis=1, how='all') # droping columns with all NaN to avoid empty sets when dropping NaN by rows at next step
    globals()[f'{key}'] = globals()[f'{key}'].dropna()  # drop rows with NaN, otherwise RandomForest won't work

    X_t = globals()[f'{key}'].drop('target', axis = 1)
    y_t = globals()[f'{key}']['target']

    X_train, X_test, y_train, y_test = train_test_split(X_t, y_t, test_size=test_size, random_state=42)
      
    rfc = RandomForestClassifier()
    rfc_random = RandomizedSearchCV(estimator = rfc, param_distributions = random_grid, n_iter = 50, cv = 3,
                                verbose = 2, random_state=42, n_jobs = -1)

    # Fitting the model
    start = time.time()
    rfc_random.fit(X_train, y_train)
    end = time.time()
    print(end - start)
    
    rf_parameters[key] = rfc_random.best_params_
    best_random = rfc_random.best_estimator_
    best_random.fit(X_train, y_train)
    
    pred = best_random.predict(X_test)
    prediction = pred[-1]
    forecast[key] = prediction
    prob = best_random.predict_proba(X_test)
    probability = prob[-1][1]
    predicted_prob[key] = probability
    acc_best_rndm = accuracy_score(y_test, pred)
    accuracy[key] = acc_best_rndm

#***************

# 00000000000000000000000000000000000000000000000
    
 # Using TUNE_SKLEARN to tune hyperparameters faster

from ray.tune.sklearn import TuneSearchCV
#from tune_sklearn import TuneSearchCV
from sklearn.model_selection import train_test_split

#accuracy = {} # Initialize a list/dictionary to store the accuracy #s for each company
#last_month = {}  # Initialize a list/dictionary to store the data for the month to be forecast by the final model
#rf_parameters = {}

#for key in price_merged.keys():
#for key in d1:
#    last_month[key] = globals()[f'{key}'][-1:].drop("target", axis = 1)
#    globals()[f'{key}'] = globals()[f'{key}'][:-1]  # drop last observation NaN on 'target'
#    globals()[f'{key}'] = globals()[f'{key}'].dropna()  # drop rows with NaN, otherwise RandomForest won't work

#    X_t = globals()[f'{key}'].drop('target', axis = 1)
#    y_t = globals()[f'{key}']['target']

#    X_train, X_test, y_train, y_test = train_test_split(X_t, y_t, test_size=test_size, random_state=42)
      
#    rfc = RandomForestClassifier()
   # if __name__ == '__main__':
#    rfc_random = TuneSearchCV(RandomForestClassifier(), param_distributions = random_grid, n_trials = 50, 
#                              n_jobs=-1,
#                              cv = 3,
                              #verbose=2,
#                              max_iters = 10,
#                              early_stopping = True,
#                              search_optimization = "random")
    
  # Fitting the model
#    start = time.time()
#    rfc_random.fit(X_train, y_train)
#    end = time.time()
#    print(end - start)
    
#    rf_parameters[key] = rfc_random.best_params_
#    best_random = rfc_random.best_estimator_
    #best_random.fit(X_train, y_train)
    
#    pred = best_random.predict(X_test)
#    prob = best_random.predict_proba(X_test)
#    acc_best_rndm = accuracy_score(y_test, pred)
#    accuracy[key] = acc_best_rndm




# GridSearch & Random Search Functions

def search(pipeline, parameters, X_train, y_train, X_test, y_test, optimizer='grid_search', n_iter=None):
    
    start = time.time() 
    
    if optimizer == 'grid_search':
        grid_obj = GridSearchCV(estimator=pipeline,
                                param_grid=parameters,
                                cv=3,
                                refit=True,
                                return_train_score=False,
                                scoring = 'accuracy',
                               )
        grid_obj.fit(X_train, y_train,)
    
    elif optimizer == 'random_search':
        grid_obj = RandomizedSearchCV(estimator=pipeline,
                            param_distributions=parameters,
                            cv=3,
                            n_iter=n_iter,
                            refit=True,
                            return_train_score=False,
                            scoring = 'accuracy',
                            random_state=42)
        grid_obj.fit(X_train, y_train,)
    
    else:
        print('enter search method')
        return

    best_estimator_grid = grid_obj.best_estimator_
    cvs = cross_val_score(best_estimator_grid, X_train, y_train, cv=3)
    results = pd.DataFrame(grid_obj.cv_results_)
    
    print("##### Results")
    print("Score best parameters: ", grid_obj.best_score_)
    print("Best parameters: ", grid_obj.best_params_)
    print("Cross-validation Score: ", cvs.mean())
    print("Test Score: ", best_estimator_grid.score(X_test, y_test))
    print("Time elapsed: ", time.time() - start)
    print("Parameter combinations evaluated: ",results.shape[0])
    
    return results, best_estimator_grid




# @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
    #@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@

    

backtest_portfolio_ret_ew = pd.DataFrame()
backtest_portfolio_ret_hrpw = pd.DataFrame()
backtest_portfolio_ret_hrpw2 = pd.DataFrame()


# 00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
# 00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
     
# *** Build portfolio for next month and compute return ***
# first we select those keys in accuracy whose forecast is 1
accuracy_df = pd.DataFrame(list(accuracy.items()))  # convert dict to dataframe
accuracy_df = accuracy_df.rename(columns={0: "stock", 1: "accuracy"})
forecast_df = pd.DataFrame(list(forecast.items()))  # convert dict to dataframe
forecast_df = forecast_df.rename(columns={0: "stock", 1: "forecast"})
probability_df = pd.DataFrame(list(predicted_prob.items()))  # convert dict to dataframe
probability_df = probability_df.rename(columns={0: "stock", 1: "probability"})
        
#    accuracy_forecast = accuracy_df.merge(forecast_df, on = "stock")   #  merge both datasets
accuracy_probability = accuracy_df.merge(probability_df, on = "stock")   #  merge both datasets
#    accuracy_forecast["forecast"] = accuracy_forecast.forecast.astype(float)   
accuracy_probability["probability"] = accuracy_probability.probability.astype(float)  
accuracy_probability = accuracy_probability.merge(forecast_df, on = "stock")   #  merge both datasets
accuracy_probability["forecast"] = accuracy_probability.forecast.astype(float)   

accuracy_weight = 0.5
accuracy_probability["acc_prob_weighted"] = accuracy_probability.accuracy*accuracy_weight + accuracy_probability.probability*(1-accuracy_weight)  # create a column with an average of accuracy and probability as a criterium to sort candidates  

# to avoid dropping stocks with forecast = 0, lets double sort by forecast then by accuracy
accuracy_probability = accuracy_probability.sort_values(['forecast','acc_prob_weighted'], ascending=[False,False]) 
    
# select best N stocks, whenever there is a minimum of N stocks with a predicted 1
best_n = 20
#if accuracy_probability.forecast.sum()==0:
#    continue

count_ones = accuracy_probability['forecast'].value_counts()[1]   # how many 1s do we have??
rf_top_stocks = accuracy_probability.stock[:min(count_ones,best_n)]
    # retrieve their returns on last month
last_month_ret = pd.DataFrame()
for stock in rf_top_stocks:
    last_month_ret[stock] = last_month[stock]['returns']
    
# compute portfolio's returns (equal weight)
equal_weight = pd.DataFrame(1/min(count_ones,best_n), index=np.arange(1), columns=np.arange(min(count_ones,best_n)))
last_month_ret['equal_w_portfolio_ret'] = np.dot(last_month_ret[rf_top_stocks],equal_weight.T)
    
# Compute HIERARCHICAL RISK PARITY weights, version 2

prices_for_hrp_top = prices_for_hrp[rf_top_stocks][0:(len(prices)-1)] # take price data up to last month available for forecasting
returns_for_hrp = prices_for_hrp_top.pct_change()
cov, corr = returns_for_hrp.cov(), returns_for_hrp.corr()


# Function for HIERARCHICAL RISK PARITY
    
def hrp_weights(returns):
    #w=pd.Series(pypfopt.hierarchical_portfolio.HRPOpt(returns).optimize())
    w=pd.Series(HRPOpt(returns).optimize())
    return w


if len(rf_top_stocks)==1:
    hierarchical_rp_w = 1
    last_month_ret['hierarchical_rp_w_portfolio_ret'] = last_month_ret[rf_top_stocks]
    hierarchical_rp_w2 = 1
    last_month_ret['hierarchical_rp_w2_portfolio_ret'] = last_month_ret[rf_top_stocks]
else:
    hierarchical_rp_w = hrp_weights(returns_for_hrp)
    last_month_ret['hierarchical_rp_w_portfolio_ret'] = np.dot(last_month_ret[rf_top_stocks],hierarchical_rp_w.T)
 


#################################################################

# *** NEXT STEPS

# 1. Backtest
# 2. Try different weighting schemes
# 3. Try different parameterizations for the Random Forest
# 4. Add more stocks, features
