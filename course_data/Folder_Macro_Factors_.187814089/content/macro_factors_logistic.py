# 
"""
# Macro Factors

@author: jose suarez-lledo
revised: 12 jan 23

 
"""


import datetime
import numpy as np
import pandas as pd
import sklearn
#pip install pandas_datareader
from pandas_datareader import DataReader
import yfinance as yf
import matplotlib.pyplot as plt
import seaborn
#%load_ext autoreload
#%autoreload 2
#%matplotlib qt

from datetime import datetime
today = datetime.today().strftime('%Y-%m-%d')


tickers = ['SPY', 'AGG', 'HYT', 'LQD', 'USO', 'GLD', 'XLK', 'XLP', 'XLF', 'XLI']
# If we want a global index, the iShares MSCI ACWI is very common but with data from April 2008. 
# Another option is World ex US: Vanguard FTSE All-World ex-US Index Fund ETF Shares (VEU), with data from 2007.
n = len(tickers)
# You can define a generic period in years '15 years'
#ETF_data = yf.download(tickers, period = "15y", interval= "1mo", start="2000-01-01", end="2020-03-31")
# or a specific time period

ETF_data = yf.download(tickers, interval= "1mo", start="2000-01-01", end="2020-03-31", auto_adjust=False)
#ETF_data = ETF_data.filter(like='Close',axis=1).iloc[:,n:2*n]

ETF_data = yf.download(tickers, interval= "1mo", start="2000-01-01", end="2020-03-31", auto_adjust=False)['Close']

ETF_data = ETF_data.dropna()
ETF_data = ETF_data.reset_index() # convert index to column (date)
ETF_data = ETF_data.rename(columns={'Date':'date'})

# This downloads data in multiIndex format 
# so here we change it to standard format removing the 2nd row and keeping the ticker
#ETF_data.columns = ['_'.join(x) for x in ETF_data.columns]
#ETF_data.columns = ETF_data.columns.str.lstrip('Close_')
#ETF_data = ETF_data.rename(columns={'date_':'date'})
#ETF_data['date'] = ETF_data['date'].dt.strftime('%Y-%m-%d')
ETF_data['date'] = pd.to_datetime(ETF_data['date'])
ETF_data['date'] = ETF_data['date'].dt.strftime('%Y-%m-%d')


# Importing macro factors 
import os
os.chdir('C:/Users/joses/OneDrive/Desktop/ESADE/Asset Management/SESSIONS/5_Strategies_w_Factors/')
macro_factors = pd.read_csv("Data/fred_data_macro_factors.csv")

n_macro_factors = len(macro_factors.columns)-1 # '-1' 
n_dates = len(macro_factors)
macro_factors['date'] = pd.to_datetime(macro_factors['date'], format='%d/%m/%Y')
macro_factors['date'] = macro_factors['date'].dt.strftime('%Y-%m-%d')

macro_etf_df = pd.merge(macro_factors, ETF_data, on = 'date') 

# 
""" 
In both linear regression and logistic regression, it is usually convenient to use stationary exogenous inputs/drivers/variables 
because modeling econometrically prices instead of growth rates has serious problems of parameter estimation that make the model very unreliable.

In this case, we are going to model growth rates (returns), so we are going to calculate them

"""

macro_etf_df.XLK.plot()
plt.show()

macro_etf_df.XLK.hist()
plt.show()

macro_etf_df_mom = macro_etf_df[macro_etf_df.columns[~macro_etf_df.columns.isin(['date'])]].pct_change()
macro_etf_df_mom = macro_etf_df_mom.add_suffix('_mom') # 

macro_etf_df_mom.XLK_mom.plot()
plt.show()

macro_etf_df_mom.XLK_mom.hist()
plt.show()

# Augmented Dickey-Fuller Test
from statsmodels.tsa.stattools import adfuller

dickey_fuller = adfuller(macro_etf_df.XLK)
print('ADF Statistic: %f' % dickey_fuller[0])
print('p-value: %f' % dickey_fuller[1])

dickey_fuller = adfuller(macro_etf_df_mom.XLK_mom.dropna())
print('ADF Statistic: %f' % dickey_fuller[0])
print('p-value: %f' % dickey_fuller[1])

# join this DF to the old one for later use 
macro_etf_df = macro_etf_df.join(macro_etf_df_mom)
macro_etf_df = macro_etf_df.dropna()

# We can start modelling now
import statsmodels.api as sm
from linearmodels import PanelOLS
from linearmodels import RandomEffects
from linearmodels.panel import PooledOLS
# LinearRegression
from sklearn.linear_model import LinearRegression

# First define variables that we want to model (Y) and those that will be factors/drivers (X)
X = macro_etf_df[["commodities_mom", "cpi_mom", "real_rate_mom","ip_mom","credit_mom","retail_sales_mom"]]
y = macro_etf_df[["AGG_mom", "GLD_mom", "HYT_mom","LQD_mom","SPY_mom","USO_mom","XLF_mom","XLI_mom","XLK_mom","XLP_mom"]]

# Just as a first approach we split the sample in training and test in a time linear manner
X_train = X.iloc[0:160,]
y_train = y.iloc[0:160,]

X_test = X.iloc[160:len(X),]
y_test = y.iloc[160:len(X),]

# 
""" Classic question when estimating a linear regression:
Do we include a constant or not? One way to decide is by examining the histograms of the variables
"""

y[["HYT_mom"]].plot.hist(grid=True, color='#607c8e')
X[["cpi_mom"]].plot.hist(grid=True, color='#607c8e')

#model = LinearRegression(fit_intercept=True).fit(X_train,y_train)

# We can obtain several metrics on the quality of the model, like R2:
macro_factors_model = LinearRegression().fit(X_train,y_train.SPY_mom)
predict = macro_factors_model.predict(X_test)

macro_factors_model.score(X_train, y_train.SPY_mom)  

#from statsmodels.sandbox.regression.predstd import wls_prediction_std

# ((((((((((((((((((((((((((((()))))))))))))))))))))))))))))
"""
 One possible strategy would be to extract the p-values to evaluate which factors are more important at each stage of the cycle, 
 in order to position oneself accordingly in each phase of the cycle. If in a specific month the real interest rate, for example, 
 is more important (lower p-value) and the fixed income ETF or utility ETF are more related to that factor, we can overweight them. 
 This strategy is somewhat simple, but it could work well. Would you be able to see its disadvantages? How would you implement it?
"""

stats_model = sm.OLS(y_train['AGG_mom'], X_train).fit()
print(stats_model.params)
print(str(stats_model.summary()))
print(stats_model.pvalues[0]) # to retrieve the p-values, [0] for the 1st, [1] for the 2nd...

#from sklearn.feature_selection import chi2

# ((((((((((((((((((((((((((()))))))))))))))))))))))))))
"""
 The previous strategy would be backward-looking. But the next one would be forward-looking.

MAIN IDEA: predict returns for 1 period, rank ETFs from highest to lowest
return (according to prediction) and position oneself in those ETFs with the highest return (prediction).

But predicting returns (figures) can be a complicated or imprecise task. A method that can help
here is LOGISTIC REGRESSION, which predicts the probability that a return will be, for example, positive or
negative at a specific horizon
"""

from sklearn.linear_model import LogisticRegression

# What we are trying to predict in this case are 1s or 0s, that is, 1 = return_t+1 >0. 
# Therefore, first we have to create a target variable that is 1 when the return is >0 and 0 in all other cases

y_ind = pd.DataFrame()
for col in y.columns:
    y_ind[col+'_ind'] = (y[col]>0.0025).astype(int)

# 
"""
We create lags of the variables for the exogenous side (X). Why? To avoid LOOK-AHEAD bias. 
We cannot use the variables in the same period as the variable we model (the endogenous variable, y) because
 with the information we have about X at t, we take a position in y for the next period, t+1.
"""

X_lag = X.shift() 
y_lag = y.shift() 

# In case we wanted to add more variables to the X Matrix:
# X_lag = pd.concat([X1, X2], axis=1) # concatenate the variables in the same DF

n_etf = n
n_lags = 1

# Will use the lag of the macro factors and lag of the returns of the variable of interest (here AGG for ex)
# WE NEED the .dropna() here otherwise the estimation will give an error (but DFs will be aligned)
X_train = pd.concat([X_lag.iloc[0:160,], y_lag.loc[0:160,'AGG_mom']], axis=1).dropna() 
y_train = y_ind.loc[0:160,'AGG_mom_ind']  # CON .ILOC: y_train = y_ind.iloc[0:160,0]

X_test = pd.concat([X_lag.iloc[160:len(X),], y_lag.loc[160:len(X),'AGG_mom']], axis=1).dropna()  
y_test = y_ind.loc[160:len(X),'AGG_mom_ind']

# 1st model with all drivers AGG
macro_factors_model_logit = LogisticRegression(fit_intercept=False).fit(X_train,y_train[n_lags:])  # Intercept False as inputs are already 0-centered
predict_logit = macro_factors_model_logit.predict(X_test)

model_prob_0_1 = macro_factors_model_logit.predict_proba(X_test)

# 2nd model eliminar commodities, real_rate
macro_factors_model_logit = LogisticRegression(fit_intercept=False).fit(X_train[X_train.columns[~X_train.columns.isin(['commodities_mom', 'real_rate_mom'])]],y_train[n_lags:])  # Intercept False as inputs are already 0-centered
predict_logit = macro_factors_model_logit.predict(X_test[X_test.columns[~X_test.columns.isin(['commodities_mom', 'real_rate_mom'])]])

logit_param = sm.Logit(y_train[n_lags:],X_train[X_train.columns[~X_train.columns.isin(['commodities_mom', 'real_rate_mom'])]]).fit()
print(logit_param.summary2())

# Matrix with actual predicted probabilities of output being 0 or 1

model_prob_0_1 = macro_factors_model_logit.predict_proba(X_test[X_test.columns[~X_test.columns.isin(['commodities_mom', 'real_rate_mom'])]])
model_prob_0_1
#####################################################################################################

# Model for the SPY (adding 2 lags of y)

X_train = pd.concat([X_lag.iloc[0:160,], y_lag.loc[0:160,'SPY_mom'], y_lag.loc[0:160,'SPY_mom'].shift(1)], axis=1).dropna() 
# Need to change the names of the columns added since they are called the same when we concatenate them
X_train.columns = ['commodities_mom', 'cpi_mom', 'real_rate_mom', 'ip_mom', 'credit_mom', 'retail_sales_mom', 'SPY_mom_lag1', 'SPY_mom_lag2']
#X_train.columns.values[X_train.shape[1]-1] = 'SPY_mom_lag2'
#X_train.columns.values[X_train.shape[1]-2] = 'SPY_mom_lag1'
y_train = y_ind.loc[0:160,'SPY_mom_ind']  # CON .ILOC: y_train = y_ind.iloc[0:160,0]

X_test = pd.concat([X_lag.iloc[160:len(X),], y_lag.loc[160:len(X),'SPY_mom'], y_lag.loc[160:len(X),'SPY_mom'].shift(1)], axis=1).dropna()  
X_test.columns.values[X_train.shape[1]-1] = 'SPY_mom_lag2'
X_test.columns.values[X_train.shape[1]-2] = 'SPY_mom_lag1'
y_test = y_ind.loc[160:len(X),'SPY_mom_ind']


# 1st model with all the drivers SPY
n_lags = 2
macro_factors_model_logit = LogisticRegression(fit_intercept=False).fit(X_train,y_train[n_lags:])  # Intercept False as inputs are already 0-centered
predict_logit = macro_factors_model_logit.predict(X_test)

logit_param = sm.Logit(y_train[n_lags:],X_train).fit()
print(logit_param.summary2())

# A popular method here is 'sequential estimation': 1st step estimate the model with just one driver, you try all of them one by one: select the best
# 2nd step, add a second driver: try all of the remaining factors one by one and keep the best, and so on so forth

macro_factors_model_logit = LogisticRegression(fit_intercept=False).fit(X_train[X_train.columns[~X_train.columns.isin(['commodities_mom','real_rate_mom','retail_sales_mom','credit_mom','SPY_mom_lag1'])]],y_train[n_lags:])  # Intercept False as inputs are already 0-centered
predict_logit = macro_factors_model_logit.predict(X_test[X_test.columns[~X_test.columns.isin(['commodities_mom','real_rate_mom','retail_sales_mom','credit_mom','SPY_mom_lag1'])]])

logit_param = sm.Logit(y_train[n_lags:],X_train[X_train.columns[~X_train.columns.isin(['commodities_mom','real_rate_mom','retail_sales_mom','credit_mom','SPY_mom_lag1','SPY_mom_lag2'])]]).fit()
print(logit_param.summary2())

# Matrix with the probabilities (forecast) 0 o 1

model_prob_0_1 = macro_factors_model_logit.predict_proba(X_test[X_test.columns[~X_test.columns.isin(['commodities_mom','real_rate_mom','retail_sales_mom','credit_mom','SPY_mom_lag1'])]])

################################################################################



# With explicit formula
X_train = pd.concat([X_lag.iloc[0:160,], y_lag.loc[0:160,]], axis=1).dropna() 
# dropna since when you join with y_lag the first row of X_lag is NaN
y_train = y_ind.loc[0:160,]  

X_test = pd.concat([X_lag.iloc[160:len(X),], y_lag.loc[160:len(X),]], axis=1).dropna()  
y_test = y_ind.loc[160:len(X),]

import statsmodels.formula.api as smf
data_logit_train = pd.concat((X_train, y_train), axis=1).dropna()
data_logit_test = pd.concat((X_test, y_test), axis=1).dropna()

# include '-1' to remove the constant
f = 'AGG_mom_ind ~ -1 + commodities_mom + cpi_mom + ip_mom + retail_sales_mom + credit_mom + real_rate_mom'
model_logit = smf.logit(formula  = str(f), data=data_logit_train).fit()

print(model_logit.summary())
print(model_logit.pvalues.iloc[0]) # to retrieve p-values, 

# FOR LOOP to retrieve p-values for each driver and select the best one
Logit_drivers = list(X_train.columns)

for j in Logit_drivers:
    #f = 'AGG_mom_ind ~ -1 + str(j)'   
    model_logit = smf.logit(formula  = f'AGG_mom_ind ~ -1 + {j}', data=data_logit_train).fit()

    print(model_logit.summary())
    print(model_logit.pvalues.iloc[0]) # 


# Extracting probabilidades
model_prob_0_1 = model_logit.predict() # they come ordered from 0 to .... instead of X_train
# To predict "UP" or "DOWN"
predictions = [ 0 if x < 0.5 else 1 for x in model_prob_0_1]
pred_mat = model_logit.pred_table(threshold=0.5)
#
"""
(0,0) True negatives
(1,1) True Positives
(0,1) False positive (predicted as 1, wrong)
(1,0) False negative (predicted as 0, wrong)
"""

# Normally a straightforward indicator of accuracy is the # of correct predictions out of the total # of predictions
(pred_mat[0,0]+pred_mat[1,1])/pred_mat.sum()

# 
"""
Other indicators:
    
Sensitivity (recall, true positive rate): #true positives (1,1) / #total positives (1,1)+(1,0) = TP / (TP + FN)
Ability to correctly label positives, high sensitivity

Specificity (true negative rate): #true negatives (0,0) / #total negatives (0,0)+(0,1)  = TN / (TN + FP)
Ability to correctly label negatives, high specificity

Precision: TP / (TP + FP)
Ability to not label as positive something that is negative (if you label too often as 1 and there are many 0s precision will be low)

Accuracy: (TP + TN) / Total Observations

F1-score: 2*(Precision*Recall/(Precision + Recall))

    
https://towardsdatascience.com/evaluating-categorical-models-e667e17987fd
https://towardsdatascience.com/evaluating-categorical-models-ii-sensitivity-and-specificity-e181e573cff8
https://realpython.com/logistic-regression-python/
https://towardsdatascience.com/building-a-logistic-regression-in-python-step-by-step-becd4d56c9c8
https://towardsdatascience.com/how-do-you-check-the-quality-of-your-regression-model-in-python-fa61759ff685
"""

# Generating confusion matrix to assess accuracy of the model
from sklearn.metrics import confusion_matrix, classification_report
print (confusion_matrix(data_logit_train.loc[1:160,'AGG_mom_ind'], predictions))

# More complete report
print(classification_report(data_logit_train.loc[1:160,'AGG_mom_ind'], predictions))
# Mannually calculate for ex Specificity
pred_mat[0,0]/(pred_mat[0,0]+pred_mat[0,1]) # Specificity
pred_mat[1,1]/(pred_mat[1,1]+pred_mat[1,0]) # Recall
pred_mat[1,1]/(pred_mat[1,1]+pred_mat[0,1]) # Precision 

# In standard regression estimations normally look at MSE o RMSE


# OUT-OF-SAMPLE PREDICTIONS
model_prob_0_1_out = model_logit.predict(X_test)
# code to predict "UP" or "DOWN"
predictions_out = [ 0 if x < 0.5 else 1 for x in model_prob_0_1_out]

print(classification_report(data_logit_test.loc[160:len(X),'AGG_mom_ind'], predictions_out))

# ROC Curve (Receiver Operating Characteristic): Compare predictions with those of a random classifier

from sklearn.metrics import roc_auc_score
from sklearn.metrics import roc_curve

# False Positive Rate: FP / (FP + TN)   Ability of the model to not get it wrong with the negatives , How often does it wrongly label negatives

# Normally ROC AUC with the test sample but here we've got few data points so train sample
logit_roc_auc = roc_auc_score(data_logit_train.loc[1:160,'AGG_mom_ind'], predictions)
fpr, tpr, thresholds = roc_curve(data_logit_train.loc[1:160,'AGG_mom_ind'], model_logit.predict(X_train))
plt.figure()
plt.plot(fpr, tpr, label='Logistic Regression (area = %0.2f)' % logit_roc_auc)
plt.plot([0, 1], [0, 1],'r--')
plt.xlim([0.0, 1.0])
plt.ylim([0.0, 1.05])
plt.xlabel('False Positive Rate')
plt.ylabel('True Positive Rate')
plt.title('Receiver operating characteristic')
plt.legend(loc="lower right")
plt.savefig('Log_ROC')
plt.show()

# How would things change with a higher threshold for y_ind 1s and 0s??

y_ind.AGG_mom_ind.hist()
y_ind.AGG_mom_ind.mean()

# MMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMM

# 
"""
From here, we build ETF portfolios based on the predictive models.

a. We build a model to predict each ETF for 1-period (month).
b. We assemble a portfolio each month by assigning weights based on these predictions.
c. We monitor the portfolio: every month we calculate the portfolio's return and other metrics.

Ideally, we would have a 'for-loop' for the variables, but to save time and show an example, each model will be a function of all the drivers
""" 


# AGG 
f = 'AGG_mom_ind ~ -1 + commodities_mom + cpi_mom + ip_mom + retail_sales_mom + credit_mom + real_rate_mom'
logit_AGG = smf.logit(formula  = str(f), data=data_logit_train).fit()
 # retrieving probabilities
logit_prob_AGG = logit_AGG.predict()
# code to predict "UP" or "DOWN"
predictions_AGG = [ 1 if x < 0.5 else 0 for x in logit_prob_AGG]

# OUT-OF-SAMPLE PREDICTIONS
AGG_prob_out = logit_AGG.predict(X_test)
# code to predict "UP" or "DOWN"
AGG_out = [ 0 if x < 0.5 else 1 for x in AGG_prob_out]


# GLD
f = 'GLD_mom_ind ~ -1 + commodities_mom + cpi_mom + ip_mom + retail_sales_mom + credit_mom + real_rate_mom'
logit_GLD = smf.logit(formula  = str(f), data=data_logit_train).fit()
 # retrieving probabilities
logit_prob_GLD = logit_GLD.predict()
 # code to predict "UP" or "DOWN"
predictions_GLD = [ 1 if x < 0.5 else 0 for x in logit_prob_GLD]

# OUT-OF-SAMPLE PREDICTIONS
GLD_prob_out = logit_GLD.predict(X_test)
# code to predict "UP" or "DOWN"
GLD_out = [ 0 if x < 0.5 else 1 for x in GLD_prob_out]



# HYT
f = 'HYT_mom_ind ~ -1 + commodities_mom + cpi_mom + ip_mom + retail_sales_mom + credit_mom + real_rate_mom'
logit_HYT = smf.logit(formula  = str(f), data=data_logit_train).fit()
# retrieving probabilities
logit_prob_HYT = logit_HYT.predict()
# code to predict "UP" or "DOWN"
predictions_HYT = [ 1 if x < 0.5 else 0 for x in logit_prob_HYT]

# OUT-OF-SAMPLE PREDICTIONS
HYT_prob_out = logit_HYT.predict(X_test)
# code to predict "UP" or "DOWN"
HYT_out = [ 0 if x < 0.5 else 1 for x in HYT_prob_out]


# LQD
f = 'LQD_mom_ind ~ -1 + commodities_mom + cpi_mom + ip_mom + retail_sales_mom + credit_mom + real_rate_mom'
logit_LQD = smf.logit(formula  = str(f), data=data_logit_train).fit()
# retrieving probabilities
logit_prob_LQD = logit_LQD.predict()
# code to predict "UP" or "DOWN"
predictions_LQD = [ 1 if x < 0.5 else 0 for x in logit_prob_LQD]

# OUT-OF-SAMPLE PREDICTIONS
LQD_prob_out = logit_LQD.predict(X_test)
# code to predict "UP" or "DOWN"
LQD_out = [ 0 if x < 0.5 else 1 for x in LQD_prob_out]


# SPY
f = 'SPY_mom_ind ~ -1 + commodities_mom + cpi_mom + ip_mom + retail_sales_mom + credit_mom + real_rate_mom'
logit_SPY = smf.logit(formula  = str(f), data=data_logit_train).fit()
# retrieving probabilities
logit_prob_SPY = logit_SPY.predict()
# code to predict "UP" or "DOWN"
predictions_SPY = [ 1 if x < 0.5 else 0 for x in logit_prob_SPY]

# OUT-OF-SAMPLE PREDICTIONS
SPY_prob_out = logit_SPY.predict(X_test)
# code to predict "UP" or "DOWN"
SPY_out = [ 0 if x < 0.5 else 1 for x in SPY_prob_out]


# USO
f = 'USO_mom_ind ~ -1 + commodities_mom + cpi_mom + ip_mom + retail_sales_mom + credit_mom + real_rate_mom'
logit_USO = smf.logit(formula  = str(f), data=data_logit_train).fit()
# retrieving probabilities
logit_prob_USO = logit_USO.predict()
# code to predict "UP" or "DOWN"
predictions_USO = [ 1 if x < 0.5 else 0 for x in logit_prob_USO]

# OUT-OF-SAMPLE PREDICTIONS
USO_prob_out = logit_USO.predict(X_test)
# code to predict "UP" or "DOWN"
USO_out = [ 0 if x < 0.5 else 1 for x in USO_prob_out]


# XLF
f = 'XLF_mom_ind ~ -1 + commodities_mom + cpi_mom + ip_mom + retail_sales_mom + credit_mom + real_rate_mom'
logit_XLF = smf.logit(formula  = str(f), data=data_logit_train).fit()
 # retrieving probabilities
logit_prob_XLF = logit_XLF.predict()
 # code to predict "UP" or "DOWN"
predictions_XLF = [ 1 if x < 0.5 else 0 for x in logit_prob_XLF]

# OUT-OF-SAMPLE PREDICTIONS
XLF_prob_out = logit_XLF.predict(X_test)
# code to predict "UP" or "DOWN"
XLF_out = [ 0 if x < 0.5 else 1 for x in XLF_prob_out]


# XLI
f = 'XLI_mom_ind ~ -1 + commodities_mom + cpi_mom + ip_mom + retail_sales_mom + credit_mom + real_rate_mom'
logit_XLI = smf.logit(formula  = str(f), data=data_logit_train).fit()
 # retrieving probabilities
logit_prob_XLI = logit_XLI.predict()
 # code to predict "UP" or "DOWN"
predictions_XLI = [ 1 if x < 0.5 else 0 for x in logit_prob_XLI]

# OUT-OF-SAMPLE PREDICTIONS
XLI_prob_out = logit_XLI.predict(X_test)
# code to predict "UP" or "DOWN"
XLI_out = [ 0 if x < 0.5 else 1 for x in XLI_prob_out]


# XLK
f = 'XLK_mom_ind ~ -1 + commodities_mom + cpi_mom + ip_mom + retail_sales_mom + credit_mom + real_rate_mom'
logit_XLK = smf.logit(formula  = str(f), data=data_logit_train).fit()
    # retrieving probabilities
logit_prob_XLK = logit_XLK.predict()
    # code to predict "UP" or "DOWN"
predictions_XLK = [ 1 if x < 0.5 else 0 for x in logit_prob_XLK]

# OUT-OF-SAMPLE PREDICTIONS
XLK_prob_out = logit_XLK.predict(X_test)
# code to predict "UP" or "DOWN"
XLK_out = [ 0 if x < 0.5 else 1 for x in XLK_prob_out]

# XLP
f = 'XLP_mom_ind ~ -1 + commodities_mom + cpi_mom + ip_mom + retail_sales_mom + credit_mom + real_rate_mom'
logit_XLP = smf.logit(formula  = str(f), data=data_logit_train).fit()
    # retrieving probabilities
logit_prob_XLP = logit_XLP.predict()
    # code to predict "UP" or "DOWN"
predictions_XLP = [ 1 if x < 0.5 else 0 for x in logit_prob_XLP]

# OUT-OF-SAMPLE PREDICTIONS
XLP_prob_out = logit_XLP.predict(X_test)
# code to predict "UP" or "DOWN"
XLP_out = [ 0 if x < 0.5 else 1 for x in XLP_prob_out]


#   BUILDING THE PORTFOLIO AND CALCULATING RESULTS

portf_prob = pd.DataFrame([AGG_prob_out,GLD_prob_out,HYT_prob_out,LQD_prob_out,SPY_prob_out,USO_prob_out,XLF_prob_out,XLI_prob_out,XLK_prob_out,XLP_prob_out])

portf_prob = portf_prob.transpose()
etf_tickers = ['AGG_mom', 'GLD_mom', 'HYT_mom', 'LQD_mom', 'SPY_mom', 'USO_mom', 'XLF_mom', 'XLI_mom', 'XLK_mom', 'XLP_mom']
portf_prob.columns = etf_tickers

# Allocate weights proportional to the up/down probability
sum_prob_up = np.sum(portf_prob[(portf_prob>0.5)],axis=1)
#sum_prob_down = np.sum(portf_prob[(portf_prob<=0.5)],axis=1)
sum_prob_down = np.sum(1-portf_prob[(portf_prob<=0.5)],axis=1)

portf_weights_up = portf_prob[(portf_prob>0.5)].divide(pd.DataFrame(sum_prob_up)[0], axis=0)
#portf_weights_down = -portf_prob[(portf_prob<=0.5)].divide(pd.DataFrame(sum_prob_down)[0], axis=0)
portf_weights_down = -(1-portf_prob[(portf_prob<=0.5)]).divide(pd.DataFrame(sum_prob_down)[0], axis=0)

portf_weights = portf_weights_up.fillna(portf_weights_down)

# Checking that weights add up to ZERO (if long/short) or ONE (if long only)
print(portf_weights.sum(axis=1))
test_0 = portf_weights.sum(axis=1)

# Portfolio Return
# Using .dot() for matrix multiplication
portf_return_last = portf_weights.iloc[-1,].dot(y.iloc[(len(X)-1),].transpose())   # this is for a particular point in time, last month for ex
print(portf_return_last)

# return on each test period (month)
portf_return_test = portf_weights.dot(y.iloc[160:].transpose())  # this is a 6x10 matrix times a 10x6 one = 6x6 look at the diagonal
portf_return = pd.DataFrame(np.diag(portf_return_test))

# Cumulative return
portf_cumulative_ret = (1+portf_return).cumprod()-1
print(portf_cumulative_ret*100)

# BENCHMARKING: 
# equal weight
equal_weight = pd.DataFrame(1/len(etf_tickers), index=np.arange(1), columns=np.arange(len(etf_tickers)))
equal_weight.columns = etf_tickers

portf_return_eqw = equal_weight.dot(y.iloc[160:].transpose()) 
print(portf_return_eqw)

portf_return_eqw = pd.DataFrame(portf_return_eqw.transpose())

# Cumulative return
portf_eqw_cumulative_ret = (1+portf_return_eqw).cumprod()-1
print(portf_eqw_cumulative_ret*100)


# Plotting them
portf_cumulative_ret.columns = ['Strategy Ret']
portf_cumulative_ret['date'] = portf_eqw_cumulative_ret.index

portf_eqw_cumulative_ret.columns = ['Equal Weight Ret']
portf_eqw_cumulative_ret['date'] = portf_eqw_cumulative_ret.index

fig, ax = plt.subplots()
ax.set_prop_cycle(None)

#ax2 = ax.twinx()

portf_cumulative_ret.plot(x='date', y=["Strategy Ret"], ax=ax)
portf_eqw_cumulative_ret.plot(x="date", y=["Equal Weight Ret"], ax=ax, ls="--")

plt.show()


# Performance (Out-of-sample) Metrics

# Annualized return (for long enough periods)

# Sharpe Ratio
strategy_sharpe_r = portf_return.mean()/portf_return.std()
eqw_sharpe_r = portf_return_eqw.mean()/portf_return_eqw.std()

# Drawdowns
window = len(portf_return) # period for calculations, initially I allow for the full implementation period
                            # could be for ex window = 252 (days) or 24 (months) or ...

portf_cumulative_ret_1 = 1+portf_cumulative_ret['Strategy Ret']
roll_max = portf_cumulative_ret_1.cummax() # also roll_max = portf_cumulative_ret_1.rolling(window, min_periods=1).max()  for the whole series
monthly_dd = portf_cumulative_ret_1/roll_max -1

max_dd = monthly_dd.cummin()  # also  max_dd = monthly_dd.rolling(window, min_periods=1).min()  for the whole series

plt.plot(monthly_dd, label='Monthly DD')
plt.plot(max_dd, label='Max DD')
plt.show()

# NEXT STEPS
# 
"""
1. Estimate the models correctly (sequentially, for example)
2. Add more criteria to the portfolio formation (probability + accuracy +...)
3. Add more assets or drivers
4. Test with daily data
5. Longer testing periods
6. How would you compare this asset allocation with Markowitz's?
7. .....
"""




















