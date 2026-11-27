"""Experimental boundary-only modification; historical solver remains untouched."""
import numpy as np
from numba import njit
from solver_lib import geometry, rhs as legacy_rhs, at
@njit(cache=True)
def scalar_initial(r,A,r0,w,t=0.):
    return A*(np.exp(-((r+t-r0)/w)**2)-np.exp(-((-r+t-r0)/w)**2))/r
@njit(cache=True)
def ghosts(p,q,s,r,h):
    pg=np.empty(2);qg=np.empty(2)
    for j in range(2):
        x=j+1.
        out=(1+x)*(q[-1]-p[-1])-x*(q[-2]-p[-2])
        sg=(1+x)*s[-1]-x*s[-2]
        inc=-sg/(r[-1]+x*h)
        pg[j]=.5*(inc-out);qg[j]=.5*(inc+out)
    return pg,qg
@njit(cache=True)
def get(x,i,parity,g):
    if i<0:return parity*x[-i-1]
    if i>=len(x):return g[i-len(x)]
    return x[i]
@njit(cache=True)
def face(p,q,s,r,h,a,al,M,flat,candidate):
    v=al[-1]/a[-1]
    R=r[-1]+h/2
    vb=1. if flat else 1-2*M/R
    if candidate:
        pg,qg=ghosts(p,q,s,r,h)
        return .5*(v*q[-1]+vb*qg[0]),.5*(v*p[-1]+vb*pg[0])
    return .5*v*q[-1],.5*v*p[-1]
@njit(cache=True)
def rhs3(p,q,s,r,h,flat,candidate):
    a,al,m,M=geometry(p,q,r,h,flat)
    if not np.isfinite(M):
        z=np.full_like(p,np.nan)
        return z,z,z
    v=al/a
    if not candidate:
        dp,dq=legacy_rhs(p,q,r,h,flat)
        return dp,dq,v*q
    pg,qg=ghosts(p,q,s,r,h)
    R=r[-1]+h/2
    vb=1. if flat else 1-2*M/R
    u=v*q;w=v*p;ug=vb*qg;wg=vb*pg
    n=len(r);dp=np.empty(n);dq=np.empty(n)
    for j in range(n):
        rf=(j+1)*h;lf=j*h
        ur=.5*(u[j]+get(u,j+1,1,ug));ul=.5*(u[j]+get(u,j-1,1,ug))
        wr=.5*(w[j]+get(w,j+1,-1,wg));wl=.5*(w[j]+get(w,j-1,-1,wg))
        dp[j]=(ur-ul)/h
        dq[j]=3*(rf*rf*wr-lf*lf*wl)/(rf**3-lf**3)
        dp[j]-=.02/h*(get(p,j-2,-1,pg)-4*get(p,j-1,-1,pg)+6*p[j]-4*get(p,j+1,-1,pg)+get(p,j+2,-1,pg))
        dq[j]-=.02/h*(get(q,j-2,1,qg)-4*get(q,j-1,1,qg)+6*q[j]-4*get(q,j+1,1,qg)+get(q,j+2,1,qg))
    return dp,dq,v*q
@njit(cache=True)
def advance3(p,q,s,r,h,dt,flat,candidate):
    a,b,x=rhs3(p,q,s,r,h,flat,candidate)
    c,d,y=rhs3(p+dt*a/2,q+dt*b/2,s+dt*x/2,r,h,flat,candidate)
    e,f,z=rhs3(p+dt*c/2,q+dt*d/2,s+dt*y/2,r,h,flat,candidate)
    g,k,w=rhs3(p+dt*e,q+dt*f,s+dt*z,r,h,flat,candidate)
    return p+dt*(a+2*c+2*e+g)/6,q+dt*(b+2*d+2*f+k)/6,s+dt*(x+2*y+2*z+w)/6
