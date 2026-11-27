"""Fresh generator distinct from R4B0/R4B2. Paired latent signals, variable sampling."""
import numpy as np
def ar(rng,n,rho):
    z=rng.standard_normal(n)
    for i in range(1,n):z[i]=rho*z[i-1]+np.sqrt(1-rho*rho)*z[i]
    return z
def cases(cfg):
    rng=np.random.default_rng(cfg["new_seed"])
    for sub in cfg["subtypes"]:
        for i in range(cfg["per_subtype_per_noise"]):
            n=int(rng.integers(600,1101));period=float(rng.uniform(1.2,5.6));cycles=float(rng.uniform(5,8))
            du=rng.lognormal(0,.35,n-1);u=np.r_[0,np.cumsum(du)];u/=u[-1];s=u*cycles*period
            scale=float(10**rng.uniform(-.3,.3));gap=scale*np.exp(-s[-1]);star=gap*rng.uniform(.3,3)
            t=star-scale*np.exp(-s);beta=float(rng.uniform(.6,1.4));env=np.exp(beta*(s-s[-1]))
            phase=rng.uniform(0,2*np.pi);drift=0.
            if sub=="positive":base=np.sin(2*np.pi*cycles*u+phase)
            elif sub in ("near_dss_chirp","chirp"):
                drift=float(rng.uniform(.015,.15) if sub=="near_dss_chirp" else rng.uniform(.7,4))*rng.choice([-1,1])
                base=np.sin(2*np.pi*(cycles*u+.5*drift*u*u)+phase)
            elif sub=="linear_time":base=np.sin(2*np.pi*cycles*(t-t[0])/(t[-1]-t[0])+phase)
            elif sub=="transient":base=np.exp(-.5*((u-rng.uniform(.15,.85))/rng.uniform(.06,.24))**2)*np.sin(2*np.pi*cycles*u+phase)
            else:base=.6*ar(rng,n,.97)+.4*ar(rng,n,.55)
            iid=rng.standard_normal(n);long=.7*ar(rng,n,.98)+.3*ar(rng,n,.85)
            narrow=np.sin(2*np.pi*(cycles+rng.choice([-1,1])*rng.uniform(.2,3))*u+rng.uniform(0,2*np.pi))+.25*iid
            floor=env[0]*rng.uniform(.3,2)
            for kind,z in (("iid",iid),("long_memory",long),("narrowband",narrow)):
                z=z/max(np.std(z),1e-30)
                for level in cfg["noise_levels"]:
                    raw=env*(base+level*z)+level*floor*iid
                    yield {"subtype":sub,"i":i,"kind":kind,"level":level,"truth_period":period if sub=="positive" else None,"truth_drift":drift,"s":s,"t":t,"raw":raw,"envelope":env,"star":star}
