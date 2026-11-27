"""Exact R4B6 latent generator with precommitted transition strata."""
import numpy as np
def bank(cfg,kind):
    rng=np.random.default_rng(cfg["seed"])
    for sub in cfg["classes"]:
        for i in range(cfg["n_per_class"]):
            period=float(rng.uniform(1.2,5.6));cycles=6;n=769
            u=np.linspace(0,1,n);s=u*cycles*period;ph=rng.uniform(0,2*np.pi);beta=float(rng.uniform(.6,1.4))
            drift=float(rng.uniform(.015,.15))*rng.choice([-1,1]);star=0. if i%2==0 else .5*np.exp(-s[-1])
            env=np.exp(beta*(s-s[-1]));t=star-np.exp(-s)
            if sub=="stationary":t=u.copy();env=np.ones(n);base=np.sin(2*np.pi*cycles*u+ph);truth=None
            elif sub=="near_dss_chirp":base=np.sin(2*np.pi*(cycles*u+.5*drift*u*u)+ph);truth=star
            else:base=np.sin(2*np.pi*cycles*u+ph);truth=star
            def ar(rho):
                x=rng.standard_normal(n)
                for j in range(1,n):x[j]=rho*x[j-1]+np.sqrt(1-rho*rho)*x[j]
                return x
            iid=rng.standard_normal(n);long=.7*ar(.98)+.3*ar(.85)
            narrow=np.sin(2*np.pi*(cycles+rng.choice([-1,1])*rng.uniform(.2,3))*u+rng.uniform(0,2*np.pi))+.25*iid
            draw=rng.uniform(size=n);z={"iid":iid,"long_memory":long,"narrowband":narrow}[kind];z/=max(np.std(z),1e-30)
            for level in cfg["noise_levels"]:
                if level==0 and kind!="iid":continue
                v=env*(base+level*z)
                for missing in cfg["missing"]:
                    keep=draw>=missing;keep[0]=keep[-1]=True
                    yield sub,i,level,missing,t[keep],v[keep],truth,period
