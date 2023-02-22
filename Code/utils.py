import numpy as np
import scipy as sp
import matplotlib.pyplot as plt
import math
import pypoman
from scipy.stats import bernoulli, multinomial
from scipy.stats.mstats import gmean


class Bets:
    '''
    Methods to set bets that are \eta-adaptive, data-adaptive, both, or neither.
    Currently, bets for stratum k can only depend on eta and data within stratum k

    Parameters
        ----------
        eta: float in [0,1]
            the null mean within stratum k
        x: 1-dimensional np.array of length n_k := T_k(t) with elements in [0,1]
            the data sampled from stratum k

        Returns
        ----------
        lam: a length-1 or length-n_k corresponding to \lambda_{ki} in the I-NNSM:
            \prod_{i=1}^{T_k(t)} [1 + \lambda_{ki (X_{ki} - \eta_k)]

    '''

    def lam_fixed(x, eta):
        '''
        lambda fixed to 0.75 (nonadaptive)
        '''
        lam = 0.75 * np.ones(x.size)
        return lam

    def lam_agrapa(x, eta):
        '''
        AGRAPA (approximate-GRAPA) from Section B.3 of Waudby-Smith and Ramdas, 2022
        lambda is set to approximately maximize a Kelly-like objective (expectation of log martingale)
        '''
        S = np.insert(np.cumsum(x),0,0)[0:-1]  # 0, x_1, x_1+x_2, ...,
        j = np.arange(1,len(x)+1)  # 1, 2, 3, ..., len(x)
        mu_hat = S/j
        mj = [x[0]]   # Welford's algorithm for running mean and running SD
        sdj = [0]
        for i, xj in enumerate(x[1:]):
            mj.append(mj[-1]+(xj-mj[-1])/(i+1))
            sdj.append(sdj[-1]+(xj-mj[-2])*(xj-mj[-1]))
        sdj = np.sqrt(sdj/j)
        sdj = np.insert(np.maximum(sdj,.1),0,1)[0:-1]
        lam_untrunc = (mu_hat - eta) / (sdj**2 + (mu_hat - eta)**2)
        lam_trunc = np.maximum(0, np.minimum(lam_untrunc, .75/eta))
        return lam_trunc

    def lam_trunc(x, eta):
        S = np.insert(np.cumsum(x),0,0)[0:-1]  # 0, x_1, x_1+x_2, ...,
        j = np.arange(1,len(x)+1)  # 1, 2, 3, ..., len(x)
        mu_hat = S/j
        lam_trunc = np.where(eta <= mu_hat, .75 / eta, 0)
        return lam_trunc

    def lam_smooth(x, eta):
        lam = np.exp(- eta)
        return lam

    def lam_smooth_predictable(x, eta):
        lag_mean = np.insert(np.cumsum(x),0,0)[0:-1] / np.arange(1,len(x)+1)
        lam = np.exp(lag_mean - eta)
        return lam

class Weights:
    '''
    Predictable and \eta-adaptive methods to set weights for combining across strata by summing
    Generally will be less powerful than taking products
    (see Vovk and Wang 2020 on E-value combining)

    Parameters
    ----------
        x: length-K list of length-n_k np.arrays with elements in [0,1]
            the data sampled from each stratum
        eta: length-K np.array in [0,1]^K
            the vector of null means across strata
        lam_func: callable, a function from the Bets class

    Returns
    ----------
        theta: a length-K list of convex weights
            the weights for combining the martingales as a sum I-NNSM E-value at time t

    '''
    def theta_fixed(x, eta, lam_func):
        '''
        balanced, fixed weights (usual average)
        '''
        theta = np.ones(len(eta))/len(eta)
        return theta

    def theta_max_predictable(x, eta, lam_func):
        '''
        puts all weight on the last (lagged) largest within-stratum martingale
        '''
        lag_marts = [np.prod(1 + lam_func(eta[k], x[k][:-1]) * (x[k][:-1] - eta[k])) for k in np.arange(K)]
        theta = np.zeros(len(eta))
        theta[np.argmax(lag_marts)] = 1
        return theta

    def theta_smooth_predictable(x, eta, lam_func):
        '''
        makes weights proportional to last (lagged) size of martingales
        '''
        lag_marts = [np.prod(1 + lam_func(eta[k], x[k][:-1]) * (x[k][:-1] - eta[k])) for k in np.arange(K)]
        theta = lag_marts / np.sum(lag_marts)
        return theta

def mart(x, eta, lam_func, log = True):
    '''
    betting martingale

    Parameters
    ----------
        x: length-n_k np.array with elements in [0,1]
            data
        eta: scalar in [0,1]
            null mean
        lam_func: callable, a function from the Bets class
        log: Boolean
            indicates whether the martingale should be returned on the log scale or not
    Returns
    ----------
        mart: scalar; the value of the (log) betting martingale at time n_k

    '''
    if log:
        mart = np.sum(np.log(1 + lam_func(x, eta) * (x - eta)))
    else:
        mart = np.prod(1 + lam_func(x, eta) * (x - eta))
    return mart

def intersection_mart(x, eta, lam_func, combine = "product", theta_func = None, log = True):
    '''
    an intersection martingale (I-NNSM) for a vector \eta

    Parameters
    ----------
        x: length-K list of length-n_k np.arrays with elements in [0,1]
            the data sampled from each stratum
        eta: length-K np.array or list in [0,1]
            the vector of null means
        lam_func: callable, a function from class Bets
        combine: string, either "product" or "sum"
            how to combine within-stratum martingales to test the intersection null
        theta_func: callable, a function from class Weights
            only relevant if combine == "sum", the weights to use when combining with weighted sum
        log: Boolean
            return the log I-NNSM if true, otherwise return on original scale
    Returns
    ----------
        the value of an intersection martingale that uses all the data (not running max)
    '''
    K = eta.shape[0]
    marts = np.array([mart(x[k], eta[k], lam_func, log) for k in np.arange(K)])
    if combine == "product":
        int_mart = np.sum(marts) if log else np.prod(marts)
    elif combine == "sum":
        assert theta_func is not None, "Need to specify a theta function from Weights if using sum"
        thetas = theta_func(eta, x, lam_func)
        int_mart = np.log(np.sum(thetas * marts)) if log else np.sum(thetas * marts)
    else:
        raise NotImplementedError("combine must be either product or sum")
    return int_mart

def plot_marts_eta(x, N, lam_func, combine = "product", theta_func = None, log = True, res = 1e-2):
    '''
    generate a 2-D or 3-D plot of an intersection martingale over possible values of \bs{\eta}
    the global null is always \eta <= 1/2; future update: general global nulls

    Parameters
    ----------
        x: length-K list of length-n_k np.arrays with elements in [0,1]
            the data sampled from each stratum
        N: length-K np.array of positive ints,
            the vector of stratum sizes
        lam_func: callable, a function from class Bets
        combine: string, either "product" or "sum"
            how to combine within-stratum martingales to test the intersection null
        theta_func: callable, a function from class Weights
            only relevant if combine == "sum", the weights to use when combining with weighted sum
        log: Boolean
            return the log I-NNSM if true, otherwise return on original scale
        res: float > 0,
            the resolution of equally-spaced grid to compute and plot the I-NNSM over
    Returns
    ----------
        generates and shows a plot of the value of the I-NNSM over different values of the null mean
    '''
    K = len(x)

    eta_grid = np.arange(res, 1-res, step=res)
    eta_xs, eta_ys, eta_zs, objs = [], [], [], []
    w = N / np.sum(N)
    if K == 2:
        for eta_x in eta_grid:
            eta_y = (1/2 - w[0] * eta_x) / w[1]
            if eta_y > 1 or eta_x < 0: continue
            obj = intersection_mart(x, np.array([eta_x,eta_y]), lam_func, combine, theta_func, log)
            eta_xs.append(eta_x)
            eta_ys.append(eta_y)
            objs.append(obj)
        plt.plot(eta_xs, objs, linewidth = 1)
        plt.show()
    elif K == 3:
        fig = plt.figure()
        ax = fig.add_subplot(projection='3d')
        for eta_x in eta_grid:
            for eta_y in eta_grid:
                eta_z = (1/2 - w[0]*eta_x-w[1]*eta_y)/w[2]
                if eta_z > 1 or eta_z < 0: continue
                obj = intersection_mart(x, np.array([eta_x,eta_y,eta_z]), lam_func, combine, theta_func, log)
                eta_xs.append(eta_x)
                eta_ys.append(eta_y)
                eta_zs.append(eta_z)
                objs.append(obj)
        ax.scatter(eta_xs, eta_ys, objs, c = objs)
        ax.view_init(20, 120)
        plt.show()
    else:
        raise NotImplementedError("Can only plot I-NNSM over eta for 2 or 3 strata.")

def union_intersection_mart(x, N, eta_0, lam_func, combine = "product", theta_func = None, log = True, calX = None, solver = "brute_force"):
    '''
    compute a UI-NNSM by minimizing I-NNSMs over feasible \eta

    Parameters
    ----------
        x: length-K list of length-n_k np.arrays with elements in [0,1]
            the data sampled from each stratum
        N: length-K list specifying the size of each stratum
        combine: string, either "product" or "sum"
            how to combine within-stratum martingales to test the intersection null
        lam_func: callable, a function from class Bets
            the function for setting the bets (lambda_{ki}) for each stratum / time
        theta_func: callable, a function from class Weights
            only relevant if combine == "sum", the weights to use when combining with weighted sum
        log: Boolean
            return the log UI-NNSM if true, otherwise return on original scale
        calX: np.array or length-K list of np.arrays
            specifies possible values in the population, or within each stratum\
            necessary for brute force optimization
        solver: string
            the solver to minimize the I-NNSM, currently only "brute_force" is supported
    Returns
    ----------
        the value of a union-intersection martingale using all data x
    '''
    K = len(x)
    if solver != "brute_force": NotImplementedError("Solver must be brute force, lol")
    #check if enumeration approach is feasible if not, complain






########## this is old stuff ###########
def sprt_mart(x : np.array, N : int, mu : float=1/2, eta: float=1-np.finfo(float).eps, \
              u: float=1, random_order = True):
    '''
    Finds the SPRT supermartingale sequence to test the hypothesis that the population
    mean is less than or equal to mu against the alternative that it is eta,
    for a population of size N of values in the interval [0, u].

    Generalizes Wald's SPRT for the Bernoulli to sampling without replacement and to bounded
    values rather than binary values.

    If N is finite, assumes the sample is drawn without replacement
    If N is infinite, assumes the sample is with replacement

    Data are assumed to be in random order. If not, the calculation for sampling without replacement is incorrect.

    Parameters:
    -----------
    x : binary list, one element per draw. A list element is 1 if the
        the corresponding trial was a success
    N : int
        population size for sampling without replacement, or np.infinity for
        sampling with replacement
    theta : float in (0,u)
        hypothesized population mean
    eta : float in (0,u)
        alternative hypothesized population mean
    random_order : Boolean
        if the data are in random order, setting this to True can improve the power.
        If the data are not in random order, set to False

    Returns
    -------
    terms : np.array
        sequence of terms that would be a supermartingale under the null
    '''
    if any((xx < 0 or xx > u) for xx in x):
        raise ValueError(f'Data out of range [0,{u}]')
    if np.isfinite(N):
        if not random_order:
            raise ValueError("data must be in random order for samples without replacement")
        S = np.insert(np.cumsum(x),0,0)[0:-1]  # 0, x_1, x_1+x_2, ...,
        j = np.arange(1,len(x)+1)              # 1, 2, 3, ..., len(x)
        m = (N*mu-S)/(N-j+1)                   # mean of population after (j-1)st draw, if null is true
    else:
        m = mu
    with np.errstate(divide='ignore',invalid='ignore'):
        terms = np.cumprod((x*eta/m + (u-x)*(u-eta)/(u-m))/u) # generalization of Bernoulli SPRT
    terms[m<0] = np.inf                        # the null is surely false
    return terms

def shrink_trunc(x: np.array, N: int, mu: float=1/2, nu: float=1-np.finfo(float).eps, u: float=1, \
                     c: float=1/2, d: float=100, f: float=0, minsd: float=10**-6, alternative = "upper") -> np.array:
        '''
        apply the shrinkage and truncation estimator to an array

        sample mean is shrunk towards nu, with relative weight d compared to a single observation,
        then that combination is shrunk towards u, with relative weight f/(stdev(x)).

        The result is truncated above at u-u*eps and below at mu_j+e_j(c,j)

        The standard deviation is calculated using Welford's method.


        S_1 = 0
        S_j = \sum_{i=1}^{j-1} x_i, j > 1
        m_j = (N*mu-S_j)/(N-j+1) if np.isfinite(N) else mu
        e_j = c/sqrt(d+j-1)
        sd_1 = sd_2 = 1
        sd_j = sqrt[(\sum_{i=1}^{j-1} (x_i-S_j/(j-1))^2)/(j-2)] \wedge minsd, j>2
        eta_j =  ( [(d*nu + S_j)/(d+j-1) + f*u/sd_j]/(1+f/sd_j) \vee (m_j+e_j) ) \wedge u*(1-eps)

        Parameters
        ----------
        x : np.array
            input data
        mu : float in (0, 1)
            hypothesized population mean
        eta : float in (t, 1)
            initial alternative hypothethesized value for the population mean
        c : positive float
            scale factor for allowing the estimated mean to approach m
        d : positive float
            relative weight of nu compared to an observation, in updating the alternative for each term
        f : positive float
            relative weight of the upper bound u (normalized by the sample standard deviation)
        minsd : positive float
            lower threshold for the standard deviation of the sample, to avoid divide-by-zero errors and
            to limit the weight of u
        '''
        S = np.insert(np.cumsum(x),0,0)[0:-1]  # 0, x_1, x_1+x_2, ...,
        j = np.arange(1,len(x)+1)              # 1, 2, 3, ..., len(x)
        m = (N*mu-S)/(N-j+1) if np.isfinite(N) else mu   # mean of population after (j-1)st draw, if null is true
        mj = [x[0]]                            # Welford's algorithm for running mean and running SD
        sdj = [0]
        for i, xj in enumerate(x[1:]):
            mj.append(mj[-1]+(xj-mj[-1])/(i+1))
            sdj.append(sdj[-1]+(xj-mj[-2])*(xj-mj[-1]))
        sdj = np.sqrt(sdj/j)
        sdj = np.insert(np.maximum(sdj,minsd),0,1)[0:-1] # threshold the sd, set first sd to 1
        if alternative == "upper":
            weighted = ((d*nu+S)/(d+j-1) + f*u/sdj)/(1+f/sdj)
            est = np.minimum(u*(1-np.finfo(float).eps), np.maximum(weighted,m+c/np.sqrt(d+j-1)))
        elif alternative == "lower":
            weighted = ((d*nu+S)/(d+j-1) + f*0/sdj)/(1+f/sdj)
            est = np.minimum(m-c/np.sqrt(d+j-1), np.maximum(weighted,np.finfo(float).eps))
        else:
            raise ValueError("alternative needs to be a string, either upper or lower.")
        return est


###add estimator that returns a fixed lambda

def alpha_mart(x: np.array, N: int, mu: float=1/2, eta: float=1-np.finfo(float).eps, f: float=0, u: float=1, \
               estim: callable=shrink_trunc, alternative="upper") -> np.array :
    '''
    Finds the ALPHA martingale for the hypothesis that the population
    mean is less than or equal to t using a martingale method,
    for a population of size N, based on a series of draws x.

    The draws must be in random order, or the sequence is not a martingale under the null

    If N is finite, assumes the sample is drawn without replacement
    If N is infinite, assumes the sample is with replacement

    Parameters
    ----------
    x : list corresponding to the data
    N : int
        population size for sampling without replacement, or np.infinity for sampling with replacement
    mu : float in (0,1)
        hypothesized fraction of ones in the population
    eta : float in (t,1)
        alternative hypothesized population mean
    estim : callable
        estim(x, N, mu, eta, u) -> np.array of length len(x), the sequence of values of eta_j for ALPHA

    Returns
    -------
    terms : array
        sequence of terms that would be a nonnegative supermartingale under the null
    '''
    S = np.insert(np.cumsum(x),0,0)[0:-1]  # 0, x_1, x_1+x_2, ...,
    j = np.arange(1,len(x)+1)              # 1, 2, 3, ..., len(x)
    m = (N*mu-S)/(N-j+1) if np.isfinite(N) else mu   # mean of population after (j-1)st draw, if null is true
    etaj = estim(x=x, N=N, mu=mu, nu=eta, f=f,u=u, alternative=alternative)
    with np.errstate(divide='ignore',invalid='ignore'):
        terms = np.cumprod((x*etaj/m + (u-x)*(u-etaj)/(u-m))/u)
    if alternative == "upper":
        terms[m<0] = np.inf
        terms[m>u] = 0
    elif alternative == "lower":
        terms[m<0] = 0
        terms[m>u] = np.inf
    else:
        raise ValueError("Input valid value for alternative: either upper or lower")
    return terms, m



def ucb_selector(running_T : np.array, running_n : np.array, running_mu : np.array, u : np.array, ns : np.array, running_lsm : np.array = None, prng : np.random.RandomState=None) -> int:
    '''
    stop sampling from a stratum if there is strong evidence that the null is true (a level-0.05 lower-sided test rejects)

    Parameters
    ----------
    running_t : np.array
        the current value of each stratumwise SM
    running_n : np.array
        the number of samples drawn from each stratum so far
    running_mu: np.array
        the current value of mu in each stratum
    running_lsm: np.array
        this is for compatability, nothing is done with it
    u: np.array
        the known upper bound in each stratum
    ns : np.array
        the total number of items in each stratum, or np.inf for sampling with replacement
    prng : np.Random.RandomState
        a PRNG (or seed, or none)
    '''
    available = (running_n < ns-1) & (running_mu < u)
    if np.sum(available) == 0:
        raise ValueError(f'all strata are exhausted: {running_n=} {ns=}')
    #pvalues = 1 / np.maximum(1, running_lsm)
    #pvalues = np.where(available, pvalues, 0)
    score = np.where(1/running_lsm > .05, 1, .05)
    score = np.where(available, score, 0)
    probs = score / np.sum(score)

    return np.random.choice(len(probs), p = probs)

def multinomial_selector(running_T : np.array, running_n : np.array, running_mu : np.array, u : np.array, ns : np.array, running_lsm : np.array = None, prng : np.random.RandomState=None) -> int:
    '''
    find the next stratum by random choice with probability proportional to current value of martingale

    Parameters
    ----------
    running_t : np.array
        the current value of each stratumwise SM
    running_n : np.array
        the number of samples drawn from each stratum so far
    running_mu: np.array
        the current value of mu in each stratum
    running_lsm: np.array
        this is for compatability, nothing is done with it
    u: np.array
        the known upper bound in each stratum
    ns : np.array
        the total number of items in each stratum, or np.inf for sampling with replacement
    prng : np.Random.RandomState
        a PRNG (or seed, or none)
    '''
    available = (running_n < ns-1) & (running_mu < u) # strata that aren't exhausted and where null isn't deterministically true
    if np.sum(available) == 0:
        raise ValueError(f'all strata are exhausted: {running_n=} {ns=}')
    geomean = gmean(running_T[available])
    if any(np.isposinf(running_T) & available):
        ratios = np.where(np.isposinf(running_T), 1, 0)
    else:
        ratios = running_T/geomean
    ratios = np.where(available, ratios, 0)
    probs = ratios/sum(ratios)

    return np.random.choice(len(ratios), p = probs)


def round_robin(running_T : np.array, running_n : np.array, running_mu : np.array, u : np.array, ns : np.array, running_lsm : np.array = None, prng : np.random.RandomState=None) -> int:
    '''
    find the next stratum by round robin: deterministic allocation proportional to the size of the strata

    Parameters
    ----------
    running_t : np.array
        the current value of each stratumwise SM (nothing is done with this)
    running_n : np.array
        the number of samples drawn from each stratum so far
    running_mu: np.array
        the current value of mu in each stratum
    running_lsm: np.array
        this is for compatability, nothing is done with it
    u: np.array
        the known upper bound in each stratum
    ns : np.array
        the total number of items in each stratum, or np.inf for sampling with replacement
    prng : np.Random.RandomState
        a PRNG (or seed, or none)
    '''
    available = (running_n < ns-1) & (running_mu < u) # strata that aren't exhausted and where null isn't deterministically true
    if np.sum(available) == 0:
        raise ValueError(f'all strata are exhausted: {running_n=} {ns=}')
    running_n = np.where(available, running_n, np.inf) # this makes the selector avoid strata that aren't available
    return np.argmin(running_n / ns) # ties broken by selecting first stratum where true


def stratum_selector(marts : list, mu : list, u : np.array, rule : callable, seed=None, lower_sided_marts : list=None) -> np.array:
    '''
    select the order of strata from which the samples will be drawn to construct the test SM

    Parameters
    ----------
    marts: list of K np.arrays
        each array is the test supermartingale for one stratum

    mu: list of K np.arrays
        each array is the running null mean for a stratum, corresponding to terms in marts

    u: np.array
        the known maximum values within each strata

    rule: callable
        maps three K-vectors (where K is the number of strata) to a value in {0, \ldots, K-1}, the stratum
        from which the next term will be included in the product SM.
        The rule should stop sampling from a stratum when that stratum is exhausted.
        The first K-vector is the current value of each stratumwise SM
        The second K-vector is the number of samples drawn from each stratum so far
        The third is the number of elements in each stratum, or np.inf for sampling with replacement

    lower_sided_marts: list of K np.arrays
        martingales for a lower sided test, used for the ucb_selector

    Returns
    -------
    strata : np.array
        the series of strata from which the samples are included
    T : np.array
        the resulting product test SM
    '''

    strata = np.array([])
    T = np.array([1])
    running_T = np.ones(len(marts))  # current value of each stratumwise SM
    running_n = np.zeros(len(marts)) # current index of each stratumwise SM
    running_mu = np.asarray([item[0] for item in mu]) #current value of the conditional null mean
    running_lsm = np.ones(len(marts)) # current value of the lower sided martingale, only relevant to ucb

    ns = np.zeros(len(marts))        # assumes the martingales exhaust the strata, for testing
    for i in range(len(marts)):
        ns[i] = len(marts[i])
    t = 0
    while np.any(running_n < ns-1):
        t += 1
        next_s = rule(running_T, running_n, running_mu, u, ns, running_lsm)
        running_n[next_s] += 1
        running_T[next_s] = marts[next_s][int(running_n[next_s])]
        running_mu[next_s] = mu[next_s][int(running_n[next_s])]
        if rule == ucb_selector:
            running_lsm[next_s] = lower_sided_marts[next_s][int(running_n[next_s])]
        if np.isposinf(running_T[next_s]):
            T = np.append(T, np.ones(int(sum(ns) - sum(running_n))) * np.inf) #pad with infinities
            strata = np.append(strata, np.ones(int(sum(ns) - sum(running_n))) * np.inf) #stratum = inf if no sample is drawn
            break
        elif np.all((running_mu >= u) | (running_n == ns-1)):
            T = np.append(T, np.ones(int(sum(ns) - sum(running_n))) * T[-1]) #pad with last value of martingale and stop counting, that null is true
            strata = np.append(strata, np.ones(int(sum(ns) - sum(running_n))) * np.inf)
            break
        elif np.any(running_mu <= 0):
            T = np.append(T, np.ones(int(sum(ns) - sum(running_n))) * np.inf) #pad with infinities; that null is certainly false
            strata = np.append(strata, np.ones(int(sum(ns) - sum(running_n))) * np.inf)
            break
        else:
            T = np.append(T, np.prod(running_T))
            strata = np.append(strata, next_s)
    return strata, T


def get_global_pvalue(strata: list, u_A: np.array, A_c: np.array, rule: callable):
    '''
    returns a P-value (maximized over nuisance parameter) for the global null hypothesis
    that the mean of a comparison audit population with 2 strata is equal to 1/2

    Parameters
    ----------
    strata: list of 2 np.arrays
        each np.array contains the values of a population within a stratum, to be sampled by SRSing
    u_A: np.array of length 2
        each value is the upper bound on assorters in each stratum (e.g., 1 for a plurality election)
    A_c: np.array of length 2
        the assorter mean of CVRs in each stratum, used to adjust null means
    rule: callable
        the stratum selection rule to be used, e.g., multinomial_selector

    Returns
    -------
    p_values: np.array of length N_1 + N_2
        the P-values for the entire sequence of samples comprised of the strata
    stratum_selections: np.array of length N_1 + N_2
        the stratum selected at each sample in the P-value-maximizing martingale (a different null corresponds to each index)
    null_selections: np.array
        the P-value-maximizing null in stratum 1 at each sample size
    '''
    assert len(strata) == 2, "Only works for 2 strata, input as list of 2 np.arrays." #only works for 2 strata, not clear how to scale efficiently yet

    shuffled_1 = np.random.permutation(strata[0])
    shuffled_2 = np.random.permutation(strata[1])
    N = np.concatenate((np.array([len(shuffled_1)]), np.array([len(shuffled_2)])))
    w = N/sum(N)
    epsilon = 1 / (2*np.max(N))
    raw_theta_1_grid = np.arange(epsilon, u_A[0] - epsilon, epsilon) #sequence from epsilon to u[0] - epsilon
    raw_theta_2_grid = (1/2 - w[0] * raw_theta_1_grid) / w[1]
    theta_1_grid = raw_theta_1_grid + u_A[0] - A_c[0]
    theta_2_grid = raw_theta_2_grid + u_A[1] - A_c[1]

    strata_matrix = np.zeros((len(shuffled_1) + len(shuffled_2) - 1, len(theta_1_grid)))
    intersection_marts = np.zeros((len(shuffled_1) + len(shuffled_2), len(theta_1_grid)))
    for i in range(len(theta_1_grid)):
        mart_1, mu_1 = alpha_mart(x = shuffled_1, N = N[0], mu = theta_1_grid[i], eta = u_A[0], f = .01, u = 2*u_A[0])
        mart_2, mu_2 = alpha_mart(x = shuffled_2, N = N[1], mu = theta_2_grid[i], eta = u_A[1], f = .01, u = 2*u_A[1])
        if rule == ucb_selector:
            lsm_marts_1 = alpha_mart(x = shuffled_1, N = N[0], mu = theta_1_grid[i], eta = theta_1_grid[i]/2, f = .01, u = 2*u_A[0], alternative = "lower")[0]
            lsm_marts_2 = alpha_mart(x = shuffled_2, N = N[1], mu = theta_2_grid[i], eta = theta_2_grid[i]/2, f = .01, u = 2*u_A[1], alternative = "lower")[0]
            lsm_marts = [lsm_marts_1, lsm_marts_2]
        else:
            lsm_marts = None
        strata_matrix[:,i], intersection_marts[:,i] = stratum_selector(
            marts = [mart_1, mart_2],
            mu = [mu_1, mu_2],
            u = 2*u_A,
            lower_sided_marts = lsm_marts,
            rule = rule)
    null_index = np.argmin(intersection_marts, axis = 1)
    #stratum_selections = strata_matrix[1:sum(N), null_index]
    #minimized_martingale = intersection_marts[1:sum(N), null_index]
    minimized_martingale = np.ones(sum(N))
    stratum_selections = np.ones(sum(N) - 1) * np.inf
    for i in np.arange(sum(N) - 1):
        minimized_martingale[i] = intersection_marts[i,null_index[i]]
        stratum_selections[i] = strata_matrix[i,null_index[i]]
    p_values = 1 / np.maximum(1, minimized_martingale)
    null_selections = raw_theta_1_grid[null_index]
    return p_values, stratum_selections, null_selections, intersection_marts, theta_1_grid, strata_matrix

def simulate_audits(strata: list, u_A: np.array, A_c: np.array, rule: callable, n_sims: int, alpha: float = 0.05):
    '''
    simulates n_sims audits by wrapping get_global_pvalue and returns stopping times at level alpha

    Parameters
    ----------
    strata: list of 2 np.arrays
        each np.array contains the values of a population within a stratum, to be sampled by SRSing
    u_A: np.array of length 2
        each value is the bound on assorters in the corresponding stratum
    A_c: np.array of length 2
        the assorter mean of CVRs in each stratum, used to adjust null means
    rule: callable
        the stratum selection rule to be used, e.g., multinomial_selector
    n_sims: positive integer
        the number of simulations to run
    alpha: float in (0,1)
        the risk limit for each simulated audit to stop

    Returns
    -------
    stopping_times: np.array of length n_sims
        the stopping time for each simulated audit
    '''
    stopping_times = np.zeros(n_sims)
    for i in np.arange(n_sims):
        p_values, stratum_selections, null_selections = get_global_pvalue(strata = strata, u_A = u_A, A_c = A_c, rule = rule)
        if any(p_values < alpha):
            stopping_times[i] = np.min(np.where(p_values < alpha))
        else:
            stopping_times[i] = np.inf
    return stopping_times


############## functions for betting SMG #############
def maximize_bsmg(samples, lam, N, theta = 1/2):
    '''
    maximize a stratified betting supermartingale over possible values of eta (the within-stratum means)

    Parameters
    ----------
    samples: length-K list of np.arrays
        samples from each stratum in random order
    lam: np.array of length K
        the fixed lambda (bet) within each stratum, must be in [0,1]
    N: np.array of length K
        the number of elements in each stratum in the population
    theta: double in [0,1]
        the global null mean

    prng : np.Random.RandomState
        a PRNG (or seed, or none)
    '''
    w = N / np.sum(N)
    K = len(N)
    #define constraint set for pypoman projection
    A = np.concatenate((
        np.expand_dims(w, axis = 0),
        np.expand_dims(-w, axis = 0),
        -np.identity(K),
        np.identity(K)))
    b = np.concatenate((1/2 * np.ones(2), np.zeros(K), np.ones(K)))
    sample_means = np.array([np.mean(x) for x in samples])
    log_mart = lambda eta, k: np.sum(np.log(1 + lam[k] * (samples[k] - eta[k])))
    global_log_mart = lambda eta: np.sum([log_mart(eta, k) for k in np.arange(K)])
    partial = lambda eta, k: -np.sum(lam[k] / (1 + lam[k] * (samples[k] - eta[k])))
    grad = lambda eta: np.array([partial(eta, k) for k in np.arange(K)])
    #proj = lambda eta: np.maximum(0, np.minimum(1, eta - w * (np.dot(w, eta) - theta) / np.sum(w**2)))
    proj = lambda eta: pypoman.projection.project_point_to_polytope(point = eta, ineq = (A, b))
    delta = 1e-3
    eta_l = proj(sample_means)
    step_size = 1
    counter = 0
    while step_size > 1e-20:
        counter += 1
        grad_l = grad(eta_l)
        next_eta = proj(eta_l - delta * grad_l)
        step_size = global_log_mart(eta_l) - global_log_mart(next_eta)
        eta_l = next_eta
    eta_star = eta_l
    log_mart = global_log_mart(eta_star)
    p_value = 1/np.maximum(1, np.exp(log_mart))
    return counter, eta_star, log_mart, p_value



#TO FIX
def stratified_comparison_betting(strata: list, n: np.array, u_A: np.array, A_c: np.array):
    '''
    Stratified comparison audit with betting martingale.
    Given a sample size in each stratum, randomly sample that many ballots and compute the global P-value

    Parameters
    ----------
    samples: length-K list of np.arrays
        samples from each stratum in random order
    lambda: np.array of length K
        the fixed lambda (bet) within each stratum, must be in [0,1]
    N: np.array of length K
        the number of elements in each stratum in the population
    u: np.array of length K
        the upper bound in each stratum
    theta: double in [0,1]
        the global null mean

    prng : np.Random.RandomState
        a PRNG (or seed, or none)
    '''
    #things have to be rescaled to make a betting martingale
    shuffled_strata = [np.random.permutation(strata[k])/u_A[k] for k in np.arange(len(strata))]
    N = np.array([len(stratum) for stratum in strata])
    K = len(strata)

    samples = [shuffled_strata[i][0:(n[i]-1)] for i in np.arange(len(shuffled_strata))]
    eta_star, log_mart, p_value = maximize_bsmg(samples = samples, lam = .9*np.ones(K), N = N, u = u_A, theta = 1/2)



############### functions for empirical Bernstein ###########
def eb_selector(running_a, running_n, running_b, N, u = None, eta = None, gamma = 1, run_in = 0, prng : np.random.RandomState=None) -> int:
    '''
    select the next stratum with probabilities based on running sample size, stratum weights, values for a and b, and possibly eta (the null vector)

    Parameters
    ----------
    running_a : np.array of length K
        the current value of "a" (the constants in each stratum) in the empirical Bernstein LP
    running_n : np.array of length K
        the current sample size in each stratum
    running_b : np.array of length K
        the current value of "b" (the slope vector) in the empirical Bernstein LP
    N : np.array
        the total number of items in each stratum, or np.inf for sampling with replacement
    u: positive double
        the upper bound on the population, needed for eta-specific strategies
    eta: np.array of length K
        optional, the intersection null currently being tested,
        if not defined, a heuristic strategy is used that tries to be powerful for all intersection nulls
    gamma: double in [0,1]
        tuning parameter to trade off between larger expected value for a or w/b
    run_in: positive integer
        the run in time, the time before which the selector draws strata uniformly at random

    prng : np.Random.RandomState
        a PRNG (or seed, or none)
    '''
    #available needs to be up here
    available = (running_n < N - 1)
    if np.sum(running_n) <= run_in:
        scores = np.ones(len(running_a))
        scores = np.where(available, scores, 0)
    else:
        if eta is not None:
            available = (running_n < N - 1) & (eta != u)
            #this is just the value of the martingale in each stratum
            scores = np.exp(running_a + running_b * eta)
            scores = np.where(available, scores, 0)
        else:
            w = N / np.sum(N)
            a_tilde = running_a / running_n
            a_tilde_normed = a_tilde / np.sum(a_tilde)
            wb_normed = (w/running_b) / np.sum(w/running_b)
            scores = gamma * a_tilde_normed + (1 - gamma) * wb_normed
            scores = np.where(available, scores, 0)
    probs = scores / sum(scores)
    return np.random.choice(len(probs), p = probs)


def psi_E(lam):
    '''
    function psi_E for lam \in [0,1) from page 10 of https://arxiv.org/pdf/2010.09686.pdf

    Parameters
    ----------
    lam: np.array of doubles in [0,1)
        values of tuning parameter lambda
    '''
    return -np.log(1 - lam) - lam

def v_i(samples):
    '''
    accumulating variance for EB page 10 of https://arxiv.org/pdf/2010.09686.pdf

    Parameters
    ----------
    samples: np.array of doubles in [0,1]
        random samples from a bounded population in sampling order
    '''
    running_mean = np.convolve(samples, np.ones(len(samples)) / len(samples), mode = 'valid')
    lagged_running_mean = np.append(1/2, running_mean[:-1])
    return (samples - lagged_running_mean)**2

def pm_lambda(samples, alpha = 0.05, c = 0.75):
    '''
    predictable mixture strategy for choosing lambda based on samples, from https://arxiv.org/pdf/2010.09686.pdf

    Parameters
    ----------
    samples: np.array of doubles in [0,1]
        random samples from a bounded population in sampling order
    alpha: double in (0,1)
        a tuning parameter, ideally corresponding to the level of the test (the risk limit)
    c: double in [0,1]
        a tuning parameter that thresholds lambda (see page 10 of https://arxiv.org/pdf/2010.09686.pdf)
    '''
    j = np.arange(1,len(samples)+1)
    mu_hat = [samples[0]]
    sigma_hat = [0]
    for i, xj in enumerate(samples[1:]):
        mu_hat.append(mu_hat[-1]+(xj-mu_hat[-1])/(i+1))
        sigma_hat.append(sigma_hat[-1]+(xj-mu_hat[-2])*(xj-mu_hat[-1]))
    sigma_hat = np.sqrt(sigma_hat/j)
    lag_sigma_hat = np.insert(sigma_hat,0,0.25)[0:-1]
    lam_pm = np.sqrt(2 * np.log(1/alpha) / (lag_sigma_hat**2 * j * np.log(1 + j)))
    lam_pm = np.minimum(lam_pm, c)
    return lam_pm



def get_eb_p_value(strata : list, lam = None, gamma = 1, run_in = 10, fixed_strategy = True):
    '''
    return stratified empirical Bernstein P-value for a selection strategy fixed over possible intersection nulls

    Parameters
    ----------
    strata: list of K np.arrays with elements in [0,1]
        random samples (in random order) from a strata in a bounded population
    lam: length K array of double in (0,1]
        optional tuning parameter (varying across strata, fixed across time), if unspecified defaults to predictable mixture https://arxiv.org/pdf/2010.09686.pdf
    gamma: double in [0,1]
        a tuning parameter that trades of between proportional allocation (0) and allocating to strata with large "a" (1)
    run_in: an integer
        a tuning parameter that tells the allocation how long to randomly draw samples before switching to the strategy
    '''
    N = np.array([len(x) for x in strata])
    K = len(strata)
    w = N/np.sum(N)
    u = 1
    marts = [np.ones(x) for x in N]
    if lam is None:
        lam = [pm_lambda(stratum) for stratum in strata]
    else:
        lam = [np.repeat(lam[k], N[k]) for k in np.arange(K)]
    a = [np.cumsum(lam[k]*strata[k] - psi_E(lam[k]) * v_i(strata[k])) for k in np.arange(K)]
    if fixed_strategy:
        running_n = np.zeros(K)
        running_a = np.zeros(K)
        running_b = np.zeros(K)
        running_lam = np.array([x[0] for x in lam])
        #record which strata are pulled from
        selected_strata = np.zeros(np.sum(N) - K)
        log_mart = np.zeros(np.sum(N) - K)
        eta_star_mat = np.zeros((np.sum(N) - K, K))
        i = 0
        while any(running_n < (N-1)):
            next_stratum = eb_selector(running_a = running_a, running_n = running_n, running_b = running_b, run_in = run_in, N = N, gamma = gamma)
            selected_strata[i] = next_stratum
            running_n[next_stratum] += 1
            running_lam[next_stratum] = lam[next_stratum][int(running_n[next_stratum])]
            running_a[next_stratum] = a[next_stratum][int(running_n[next_stratum])]
            running_b[next_stratum] -= running_lam[next_stratum]
            eta_star = np.zeros(K)
            active = np.ones(K)
            #greedy algorithm to optimize over eta
            while (np.dot(eta_star, w) < 1/2):
                assert all(eta_star <= u)
                weight = -running_b / w
                max_index = np.argmax(weight * active)
                active[max_index] = 0
                eta_star[max_index] = np.minimum(u, (1/2 - np.dot(eta_star, w)) / w[max_index])
            log_mart[i] = np.sum(running_a) + np.dot(running_b, eta_star)
            eta_star_mat[i,:] = eta_star
            i += 1
            mart = np.exp(log_mart)
            p_value = 1/np.maximum(1, mart)
        return log_mart, p_value, selected_strata, eta_star_mat
    else:
        #enumerate possible minimizing etas using pypoman
        A = np.concatenate((np.expand_dims(w, axis = 0), np.expand_dims(-w, axis = 0), -np.identity(K), np.identity(K)))
        b = np.concatenate((1/2 * np.ones(2), np.zeros(K), u*np.ones(K)))
        vertices = np.stack(pypoman.compute_polytope_vertices(A, b), axis = 0)
        minimizing_etas = vertices[np.matmul(vertices, w) == 1/2,]
        minimizing_etas = np.append(minimizing_etas, [[1/2,1/2,1/2]], axis = 0)
        #a log martingale for each possible minimizing eta
        log_marts = np.zeros((np.sum(N), minimizing_etas.shape[0]))
        stratum_counts = np.zeros((np.sum(N), K, minimizing_etas.shape[0]))
        #predictable interleaving for each martingale
        for v in np.arange(minimizing_etas.shape[0]):
            eta = minimizing_etas[v,]
            running_n = np.zeros(K)
            running_a = np.zeros(K)
            running_b = np.zeros(K)
            running_lam = np.array([x[0] for x in lam])
            i = 0
            while any((running_n < N - 1) & (eta != u)):
                next_stratum = eb_selector(running_a = running_a, running_n = running_n, running_b = running_b, N = N, u = u, eta = eta)
                running_n[next_stratum] += 1
                stratum_counts[i,:,v] = running_n
                running_lam[next_stratum] = lam[next_stratum][int(running_n[next_stratum])]
                running_a[next_stratum] = a[next_stratum][int(running_n[next_stratum])]
                running_b[next_stratum] -= running_lam[next_stratum]
                log_marts[i,v] = np.sum(running_a) + np.dot(running_b, eta)
                i += 1
            #carry forward the last value of the martingale and stratum counts
            log_marts[i:,v] = log_marts[i-1,v]
            stratum_counts[i:,:,v] = stratum_counts[i-1,:,v]
        min_log_mart = log_marts.min(axis = 1)
        min_index = log_marts.argmin(axis = 1)
        min_mart = np.exp(min_log_mart)
        p_value = 1/np.maximum(1, min_mart)
        return log_marts, p_value, minimizing_etas, min_index, stratum_counts

##############################################################################

def test_shrink_trunc():
    epsj = lambda c, d, j: c/math.sqrt(d+j-1)
    Sj = lambda x, j: 0 if j==1 else np.sum(x[0:j-1])
    muj = lambda N, mu, x, j: (N*mu - Sj(x, j))/(N-j+1) if np.isfinite(N) else mu
    nus = [.51, .55, .6]
    mu = 1/2
    u = 1
    d = 10
    vrand =  sp.stats.bernoulli.rvs(1/2, size=20)
    v = [
        np.array([0, 0, 0, 0, 0, 1, 1, 1, 1, 1]),
        np.array([1, 1, 1, 1, 1, 1, 0, 0, 0, 0]),
        vrand
    ]
    for nu in nus:
        c = (nu-mu)/2
        for x in v:
            N = len(x)
            xinf = shrink_trunc(x, np.inf, mu, nu, c=c, d=d)
            xfin = shrink_trunc(x, len(x), mu, nu, c=c, d=d)
            yinf = np.zeros(len(x))
            yfin = np.zeros(len(x))
            for j in range(1,len(x)+1):
                est = (d*nu + Sj(x,j))/(d+j-1)
                most = u*(1-np.finfo(float).eps)
                yinf[j-1] = np.minimum(np.maximum(mu+epsj(c,d,j), est), most)
                yfin[j-1] = np.minimum(np.maximum(muj(N,mu,x,j)+epsj(c,d,j), est), most)
            np.testing.assert_allclose(xinf, yinf)
            np.testing.assert_allclose(xfin, yfin)

def test_multinomial_selector():
    running_T = np.ones(3)
    running_n = np.zeros(3)
    pass  # fix me!

if __name__ == "__main__":
    test_shrink_trunc()
