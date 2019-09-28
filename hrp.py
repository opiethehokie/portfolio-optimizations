# by MLdP <lopezdeprado@lbl.gov>
# Hierarchical Risk Parity

import numpy as np
import pandas as pd
import scipy.cluster.hierarchy as sch

# Compute the inverse-variance portfolio
def getIVP(cov,**kargs):
  ivp=1./np.diag(cov)
  ivp/=ivp.sum()
  return ivp

# Compute variance per cluster
def getClusterVar(cov,cItems):
  cov_=cov.loc[cItems,cItems] # matrix slice
  w_=getIVP(cov_).reshape(-1,1)
  cVar=np.dot(np.dot(w_.T,cov_),w_)[0,0]
  return cVar

# Sort clustered items by distance
def getQuasiDiag(link):
  link=link.astype(int)
  sortIx=pd.Series([link[-1,0],link[-1,1]])
  numItems=link[-1,3] # number of original items
  while sortIx.max()>=numItems:
    sortIx.index=range(0,sortIx.shape[0]*2,2) # make space
    df0=sortIx[sortIx>=numItems] # find clusters
    i=df0.index;j=df0.values-numItems
    sortIx[i]=link[j,0] # item 1
    df0=pd.Series(link[j,1],index=i+1)
    sortIx=sortIx.append(df0) # item 2
    sortIx=sortIx.sort_index() # re-sort
    sortIx.index=range(sortIx.shape[0]) # re-index
  return sortIx.tolist()

# Compute HRP alloc
def getRecBipart(cov,sortIx):
  w=pd.Series(1,index=sortIx)
  cItems=[sortIx] # initialize all items in one cluster
  while len(cItems)>0:
    cItems=[i[j:k] for i in cItems for j,k in ((0, len(i) // 2), (len(i) // 2, len(i))) if len(i)>1] # bi-section
    for i in range(0,len(cItems),2): # parse in pairs
      cItems0=cItems[i] # cluster 1
      cItems1=cItems[i+1] # cluster 2
      cVar0=getClusterVar(cov,cItems0)
      cVar1=getClusterVar(cov,cItems1)
      alpha=1-cVar0/(cVar0+cVar1)
      w[cItems0]*=alpha # weight 1
      w[cItems1]*=1-alpha # weight 2
  return w

# A distance matrix based on correlation, where 0<=d[i,j]<=1
def correlDist(corr):
  dist=((1-corr)/2.)**.5 # distance matrix
  return dist

# Construct a hierarchical portfolio
def getHRP(cov,corr):
  corr,cov=pd.DataFrame(corr),pd.DataFrame(cov)
  dist=correlDist(corr).fillna(0)
  link=sch.linkage(dist,'single')
  sortIx=getQuasiDiag(link)
  sortIx=corr.index[sortIx].tolist() # recover labels
  hrp=getRecBipart(cov,sortIx)
  return hrp.sort_index()

#------------------------------------------------------------------------------

from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
import math
import requests_cache
import yfinance as yf
import warnings

from pandas_datareader import data as pdr
from scipy.cluster.hierarchy import ClusterWarning
from sklearn.covariance import LedoitWolf

yf.pdr_override()
np.random.seed(42)
warnings.filterwarnings('ignore', category=ClusterWarning)

def get_returns(tickers, start, end):
  session = requests_cache.CachedSession(backend='sqlite', expire_after=timedelta(days=1))
  data = pdr.get_data_yahoo(tickers, start=start, end=end, session=session)
  close = data['Adj Close']
  close.index = pd.to_datetime(close.index)
  #new_values = close[1:].values
  #old_values = close[:-1].values
  #return np.log(np.divide(new_values, old_values))
  #return (new_values - old_values) / old_values
  returns = close.pct_change(1).dropna()
  return returns

# https://scikit-learn.org/stable/modules/generated/sklearn.covariance.LedoitWolf.html#sklearn.covariance.LedoitWolf
def regularize_cov(returns):
  regularized_cov = LedoitWolf().fit(returns).covariance_
  return pd.DataFrame(regularized_cov, columns=returns.columns, index=returns.columns)
    
# https://blog.thinknewfound.com/2016/10/shock-covariance-system/
def perturb_returns(returns, n=1000):
  cov = regularize_cov(returns)
  #cov = returns.cov()
  perturbed_covs = []
  for i in range(n):
    eig_vals, eig_vecs = np.linalg.eig(cov)
    kth_eig_val = np.random.choice(eig_vals, p=[v / eig_vals.sum() for v in eig_vals])
    k = np.nonzero(eig_vals == kth_eig_val)
    perturbed_kth_eig_val = kth_eig_val * math.exp(np.random.normal(0, 1)) # exponential scaling
    eig_vals[k] = perturbed_kth_eig_val
    perturbed_covs.append(np.linalg.multi_dot([eig_vecs, np.diag(eig_vals), eig_vecs.T]))
  perturbed_cov = np.mean(np.array(perturbed_covs), axis=0)
  return pd.DataFrame(perturbed_cov, columns=returns.columns, index=returns.columns)

def cov2corr(cov):
  std = np.sqrt(np.diag(cov))
  return pd.DataFrame(cov / np.outer(std, std)).set_index(cov.index)

tickers = ['JPHY','LEMB','SGOL','PPEM','PDBC','PPLC','PPSC','LTPZ','VNQ','VNQI','PPDM','TMF','TYD','BTAL']
returns = get_returns(tickers, date.today() + relativedelta(months=-6), date.today())
hrps = []

cov, corr = returns.cov(), returns.corr()
hrps.append(getHRP(cov, corr))

cov = perturb_returns(returns)
corr = cov2corr(cov)
hrps.append(getHRP(cov, corr))

returns = get_returns(tickers, date.today() + relativedelta(months=-18), date.today())

cov, corr = returns.cov(), returns.corr()
hrps.append(getHRP(cov, corr))

cov = perturb_returns(returns)
corr = cov2corr(cov)
hrps.append(getHRP(cov, corr))

print(pd.concat(hrps).groupby(level=0).mean().round(3) * 100)
