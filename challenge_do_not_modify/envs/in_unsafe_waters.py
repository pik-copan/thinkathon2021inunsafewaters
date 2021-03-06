"""main challenge: navigate a boat in unknown waters so that it does not fall of a cliff for as long as possible"""

# DO NOT CHANGE!

import numpy as np
from numpy import abs, sin, cos, pi
from scipy.integrate import odeint 
from numba import njit

from gym import core, spaces
from gym.utils import seeding


# PARAMETERS:

rho_max = pi/2  # = +- 90°
m_max = 5
t_max = 3  # task: survive until this time!

radius = 1  # distance between boat's center of gravity and its motor 
c = 0.1  # dampening coefficient for dynamics

# if boundary == line:
yoff_line = -1  # offset for y dynamics

# if boundary == circle:
yoff_circle = -1  # offset for y dynamics
boundary_radius = 4  # radius of safe region 
initial_radius = 3  # range of initial positions 


# DYNAMICS:
    
@njit 
def fxfy(x, y, coeffs):
    # extract parameters:
    yoff, a00, a10, a01, a11, a20, a02, b00, b10, b01, b11, b20, b02, a30, a21, a12, a03, b30, b21, b12, b03 = coeffs
    y -= yoff
    fx = a00 + a10*x + a01*y + a11*x*y + a20*x**2 + a02*y**2 + a30*x**3 + a21*x**2*y + a12*x*y**2 + a03*y**3 - c*x*(x**2 + y**2)**1.5 
    fy = b00 + b10*x + b01*y + b11*x*y + b20*x**2 + b02*y**2 + b30*x**3 + b21*x**2*y + b12*x*y**2 + b03*y**3 - c*y*(x**2 + y**2)**1.5
    return fx, fy

@njit
def jacobian(x, y, coeffs):
    # extract parameters:
    yoff, a00, a10, a01, a11, a20, a02, b00, b10, b01, b11, b20, b02, a30, a21, a12, a03, b30, b21, b12, b03 = coeffs
    y -= yoff
    dxfx = a10 + a11*y + 2*a20*x + 3*a30*x**2 + 2*a21*x*y +   a12*y**2 - c*x * 1.5*(x**2 + y**2)**0.5 * 2*x - c * (x**2 + y**2)**1.5 
    dyfx = a01 + a11*x + 2*a02*y +   a21*x**2 + 2*a12*x*y + 3*a03*y**2 - c*x * 1.5*(x**2 + y**2)**0.5 * 2*y 
    dxfy = b10 + b11*y + 2*b20*x + 3*b30*x**2 + 2*b21*x*y +   b12*y**2 - c*y * 1.5*(x**2 + y**2)**0.5 * 2*x
    dyfy = b01 + b11*x + 2*b02*y +   b21*x**2 + 2*b12*x*y + 3*b03*y**2 - c*y * 1.5*(x**2 + y**2)**0.5 * 2*y - c * (x**2 + y**2)**1.5
    return dxfx, dyfx, dxfy, dyfy
    
@njit
def dxyphi(xyphi, unused_t, coeffs, action, strategy=None):
    # extract state:
    x,y,phi = xyphi  
    # get field:
    fx, fy = fxfy(x, y, coeffs)
    
    # extract action:
    if strategy is not None:
        action = strategy(xyphi)
    m, rho = action
    # motor force component parallel to the orientation of the boat moves the boat forward:
    forward_velocity = m * cos(rho)
    # motor force component perpendicular to the orientation of the boat turns the boat:
    turning_velocity = m * sin(rho)
    angular_velocity = turning_velocity / radius

    # derivatives:
    return [
        fx + forward_velocity * sin(phi),  # dx/dt
        fy + forward_velocity * cos(phi),  # dy/dt
        angular_velocity  # dphi/dt
        ]

@njit
def go_center_twice(xyphi0):
    # utopian strategy used in selection of scenarios only
    x,y,phi = xyphi0
    target_phi = np.arctan2(x,y) + np.pi
    m = 2*m_max
    rho = -np.sign(np.sin(phi-target_phi)) * rho_max * (np.abs(np.sin(phi-target_phi)) if np.cos(phi-target_phi) > 0 else 1)
    return np.array([m, rho])

class InUnsafeWaters(core.Env):
    """
    
    **SUMMARY:**
    
    The goal of this task is to navigate a boat in unknown waters 
    so that it does not fall off a cliff for as long as possible,
    using its motor and rudder.
    
    The waters have weird, unknown currents 
    that stay constant during each episode but change from episode to episode.

    The boat's motion is thus a combination between being dragged by these currents 
    and being pushed and/or rotated by its motor.
    
    You can access all of the parameters mentioned below via the method 
    get_parameters(), but you cannot change them.
    
    
    **STATE:**
    
    (x, y, phi) where 
        x, y are the coordinates of the boat's position.
        phi is the angle of the ship's orientation:
            phi=0: boat points towards positive y ("up" in the visualisation)
            phi=pi/2: towards positive x ("right")
            phi=pi: towards negative y ("down")
            phi=1.5pi: towards negative x ("left")


    **ACTION:**

    (m, rho) where
        m is the motor speed between 0 and m_max 
        rho is the rudder angle between -rho_max and +rho_max:
            rho=0: motor drives boat forward in the direction of its orientation (phi)
            rho=-pi/2: motor turns boat left around its center of gravity without pushing it forward
            rho=pi/2: motor turns boat right around its center of gravity without pushing it forward
            rho between -pi/2 and 0: boat somewhat turns left and somewhat pushes forward 
            rho between 0 and pi/2: boat somewhat turns right and somewhat pushes forward 

    
    **TIME STEP:**

    While the actual motion of the boat happens in continuous time, 
    the agent can only change her action n_steps many times between time 0 and t_max,
    resulting in a step size of t_max/n_steps.
    This parameter n_steps can be chosen by you when you initialize the environment.
    A smaller n_steps speeds up the simulation, a larger n_steps gives the agent more control.
    The default value of n_steps is 1000.

    
    **OBSERVATION:**

    The learner is given an array with the following entries as observation:
        0: x,
        1: y: boat position
        2: sin(phi), 
        3: cos(phi): sine and cosine of boat orientation angle
        4: D: distance to boundary
        5: sin(theta), 
        6: cos(theta): sine and cosine of direction to boundary relative to boat orientation
        7: dx/dt, 
        8: dy/dt, 
        9: dsin(phi)/dt, 
        10: dcos(phi)/dt, 
        11: dD/dt, 
        12: dsin(theta)/dt, 
        13: dcos(theta)/dt: time derivatives of all the above quantities, given the current action
        14: fx,
        15: fy: flow components at current position
        16: dfx/x,
        17: dfx/y,
        18: dfy/x,
        19: dfy/y: spatial derivative of flow (=Jacobian matrix of flow field)
        
    In this, theta=0 means the boundary is straight ahead of the boat, 
    theta=pi/2 means it is to the right of the boat,
    theta=-pi/2 means it is to the left of the boat,
    theta=pi means it is behind the boat.
        
    Angles are given as sine and cosine since otherwise the learner might get confused if the angle crosses 2pi.

    
    **TERMINATION:**

    An episode terminates as soon as y gets negative (the boat falls off the cliff)
    or the target time t_max is reached.


    **REWARD:**
    
    Before time t_max, the reward is always zero. 
    If the boat does not fall off the cliff (y<0) before time t_max, 
    it gets a final reward of 1.0 at time t_max.
    In other words, the goal is to maximize the probability of "surviving" until time t_max.

    This is the reward function used in the official evaluation 
    of the trained agent at the end of the thinkathon.
    
    During the training phase, you may want to use auxiliary reward functions
    that help the learner evaluate her actions. 
    Such an auxiliary reward functions could e.g. be the survival time 
    (i.e., assume a reward of 1 in each step).
    Another auxiliary reward function could be based on the distance to the cliff
    and give a reward of y in each step.
    
    
    **RENDERING:**
    
    The boat is shown in black, its exact position marked in white.
    The motor angle is represented by the direction of the yellow triangle,
    its speed by the triangle's size.
    The boundary is between the blue (allowed) and red (forbidden) region.
    The point on the boundary closest to the boat is marked with a red line.
    The (unobserved!) flow is indicated by dark blue arrows.
    
    """

    metadata = {
        "render.modes": ["human", "rgb_array"], 
        "video.frames_per_second": 5
    }
    
    _coeffs = None
    state0 = None

    def get_parameters(self):
        return { 'm_max': m_max, 'rho_max': rho_max, 't_max': t_max }
        
    def __init__(self, n_steps=1000, boundary='line'):
        assert n_steps > 0, "n_steps must be at least 1"
        assert boundary in ['line', 'circle']
        self.n_steps = n_steps
        self.boundary = boundary
        # agent can choose a pair [motor speed, rudder angle]:
        self.action_space = spaces.Box(
            low=np.array([0, -rho_max]), 
            high=np.array([m_max, rho_max]), dtype=np.float64)
        # agent observes the sixtuple 
        # [position x, position y, orientation angle phi, dx/dt, dy/dt, dphi/dt]:
        self.observation_space = spaces.Box(
            low=np.array([
            -np.inf, 
            -np.inf, 
            -1,
            -1,
            0, 
            -1,
            -1,
            -np.inf, 
            -np.inf, 
            -np.inf, 
            -np.inf,
            -np.inf, 
            -np.inf, 
            -np.inf, 
            -np.inf, 
            -np.inf, 
            -np.inf,
            -np.inf, 
            -np.inf, 
            -np.inf, 
            ]), 
            high=np.array([
            np.inf, 
            np.inf, 
            1,
            1,
            np.inf, 
            1,
            1,
            np.inf, 
            np.inf, 
            np.inf, 
            np.inf,
            np.inf, 
            np.inf, 
            np.inf, 
            np.inf, 
            np.inf, 
            np.inf,
            np.inf, 
            np.inf, 
            np.inf, 
            ]), dtype=np.float64)
        self.state = self.state0 = self.history = self.viewer = None
        self.n_reset_coeffs = self._n_passive_succeeds = self._n_twice_fails = 0
        self.seed()

    def seed(self, seed=None):
        self._seed = seed
        self.np_random, seed = seeding.np_random(seed)
        return [seed]

    def reset(self, same=False):
        """
        If same=True, reuse the same scenario. This may be useful in the initial
        phase of the training process. For the final evaluation, the default
        of same=False must be used.
        """
        if (not same) or (self._coeffs is None) or (self.state0 is None):
            # find a random scenario that is neither trivial nor too hard:
            ts = np.linspace(0, t_max, self.n_steps+1)
            while True:
                # choose random flow field:
                coeffs = self.np_random.normal(size=21)
                if self.boundary == 'line':
                    coeffs[0] = yoff_line
                    # choose random initial position and upwards orientation:
                    xyphi0 = np.array([6*self.np_random.uniform()-3, 6*self.np_random.uniform(), 0])
                elif self.boundary == 'circle':
                    coeffs[0] = yoff_circle
                    # choose random initial position and orientation:
                    while True:
                        x, y = initial_radius * self.np_random.uniform(-1,1,size=2)
                        if x**2 + y**2 > initial_radius**2:
                            continue
                        break
                    xyphi0 = np.array([x, y, 0])
                if self.boundary == 'line':
                    # if passive survives, don't use:
                    traj = odeint(dxyphi, xyphi0, ts, args=(coeffs, np.zeros(2)))
                    if np.all(traj[:,1] > 0):
                        self._n_passive_succeeds += 1
                        continue
                    # if moving upwards with twice the maximal speed does not survive, don't use either:
                    traj = odeint(dxyphi, np.concatenate((xyphi0[:2],[0])), ts, args=(coeffs, np.array([2*m_max, 0])))
                    if not np.all(traj[:,1] > 0): 
                        self._n_twice_fails += 1
                        continue
                elif self.boundary == 'circle':
                    # if passive survives, don't use:
                    traj = odeint(dxyphi, xyphi0, ts, args=(coeffs, np.zeros(2)))
                    if np.all(traj[:,0]**2 + traj[:,1]**2 < boundary_radius**2):
                        self._n_passive_succeeds += 1
                        continue
                    # if moving towards center with twice the maximal speed does not survive, don't use either:
                    x,y,phi = xyphi0
                    traj = odeint(dxyphi, xyphi0, ts, args=(coeffs, np.zeros(2), go_center_twice))
                    if not np.all(traj[:,0]**2 + traj[:,1]**2 < boundary_radius**2):
                        self._n_twice_fails += 1
                        continue
                # otherwise use these coeffs and initial condition
                xyphi0[2] = 2*pi * self.np_random.uniform()                    
                break
            self._coeffs = coeffs
            self.state0 = xyphi0
            self.n_reset_coeffs += 1
        self.history = []
        self.t = 0
        self.state = self.state0
        self.action = np.zeros(2)
        self.reward = 0
        self.terminal = False
        self._make_obs()
        self._remember()
        return self.obs

    def step(self, action):
        assert not self.terminal, "no steps beyond termination allowed"
        m, rho = action
        if not (0 <= m <= m_max):
            mold = m
            m = max(0, min(m, m_max))
            print("WARNING: m must be between 0 and "+str(m_max)+", so "+str(mold)+" was replaced by "+str(m))
        if not (-rho_max <= rho <= rho_max):
            rhoold = rho
            rho = max(-rho_max, min(rho, rho_max))
            print("WARNING: rho must be between +- "+str(rho_max)+ ", so "+str(rhoold)+" was replaced by "+str(rho))
        self.action = np.array(action)
        # integrate dynamics for dt time units:
        dt = t_max / self.n_steps
        new_state = odeint(dxyphi, self.state, [0, dt], (self._coeffs, self.action))[-1,:]
        new_state[0] = max(-1e9, min(new_state[0], 1e9))  # avoids nans
        new_state[1] = max(-1e9, min(new_state[1], 1e9))
        new_state[2] = wrap(new_state[2], -pi, pi)
        self.t += dt
        x,y,phi = self.state = new_state
        self._make_reward()
        self._make_obs()
        self._remember()
        return (self.obs, self.reward, self.terminal, {})

    def render(self, mode="human"):
        from gym.envs.classic_control import rendering
        
        if self.viewer is None:
            self.viewer = rendering.Viewer(800, 450)
            if self.boundary == 'line':
                self.viewer.set_bounds(-8, 8, -1, 8)
                xs = self._xs = np.linspace(-8, 8, 33)
                ys = self._ys = np.linspace(-1, 8, 19)
            elif self.boundary == 'circle':
                self.viewer.set_bounds(-8, 8, -4.5, 4.5)
                xs = self._xs = np.linspace(-8, 8, 33)
                ys = self._ys = np.linspace(-4, 4, 16)
            self._dxys = np.array([[list(dxyphi(np.array([x,y,0]),0,self._coeffs,np.zeros(2))[:2]) for y in ys] for x in xs])
            
        if self.state is None:
            return None

        # draw flow field:
        if self.boundary == 'line':
            self.viewer.draw_polygon([[-8,0],[8,0],[8,8],[-8,8]], filled=True).set_color(0.4, 0.7, 0.9)
            self.viewer.draw_polygon([[-8,0],[8,0],[8,-1],[-8,-1]], filled=True).set_color(1.0, 0.3, 0.3)
        elif self.boundary == 'circle':
            self.viewer.draw_polygon([[-8,-4.5],[8,-4.5],[8,4.5],[-8,4.5]], filled=True).set_color(1.0, 0.3, 0.3)
            c = self.viewer.draw_circle(radius=boundary_radius)
            c.set_color(0.4, 0.7, 0.9)
        for i,x in enumerate(self._xs):
            for j,y in enumerate(self._ys):
                dxy = self._dxys[i,j,:]
                dx,dy = dxy / np.sqrt((dxy**2).sum()) / 3
                self.viewer.draw_polygon([[x+dy/10, y-dx/10], 
                                          [x-dy/10, y+dx/10], 
                                          [x+dx, y+dy]], filled=True).set_color(0.3, 0.575, 0.675)

        x,y,phi = self.state
        m,rho = self.action
        
        # draw link to closest boundary point:
        li = self.viewer.draw_line([(x+self._bx)/2, (y+self._by)/2], [self._bx, self._by])
        li.set_color(1.0, 0.3, 0.3)

        # draw boat:
        dx = radius * sin(phi)
        dy = radius * cos(phi)
        b = self.viewer.draw_polygon([[x+dy/5, y-dx/5], 
                                      [x-dx, y-dy], 
                                      [x-dy/5, y+dx/5], 
                                      [x+dx, y+dy]])
        b.set_color(0, 0, 0)
        # draw boat's center of gravity:
        c = self.viewer.draw_circle(radius=0.15)
        c.add_attr(rendering.Transform(translation=(x, y)))
        c.set_color(1, 1, 1)
        c = self.viewer.draw_circle(radius=0.05)
        c.add_attr(rendering.Transform(translation=(x-dx, y-dy)))
        c.set_color(0, 0, 0)
        # draw motor:
        motorlen = m/m_max * radius/2
        dx2 = motorlen * sin(phi-rho)
        dy2 = motorlen * cos(phi-rho)
        mo = self.viewer.draw_polygon([[x-dx-dx2/2+dy2/3, y-dy-dy2/2-dx2/3], 
                                       [x-dx-dx2/2-dy2/3, y-dy-dy2/2+dx2/3], 
                                       [x-dx+dx2/2, y-dy+dy2/2]])
        mo.set_color(1, 1, 0)
        
        return self.viewer.render(return_rgb_array=mode == "rgb_array")

    def close(self):
        if self.viewer:
            self.viewer.close()
            self.viewer = None

    def _make_reward(self):
        x,y,phi = self.state
        if self.boundary == 'line':
            died = (y <= 0)
        elif self.boundary == 'circle':
            died = (x**2 + y**2 >= boundary_radius**2)
        self.terminal = (died or (self.t >= t_max))
        self.reward = 1.0 if self.terminal and not died else 0.0
        
    def _make_obs(self):
        # agents can observe the full state, the distance from the boundary,
        # and all these quantities' time derivatives, the current flow and its
        # Jacobian, but cannot observe the full flow parameters:
        x,y,phi = s = self.state
        dx,dy,dphi = ds = dxyphi(self.state, self.t, self._coeffs, self.action)
        # transform angle:
        sinphi = np.sin(phi)
        cosphi = np.cos(phi)
        dsinphi = cosphi * dphi
        dcosphi = -sinphi * dphi
        # find closest point bx,by on boundary and its time derivative dbx,dby:
        if self.boundary == 'line':
            bx = x
            by = 0
            dbx = dx
            dby = 0
        elif self.boundary == 'circle':
            R = np.sqrt(x**2 + y**2)  # distance from origin
            dR = (x*dx + y*dy) / R
            fac = boundary_radius / R
            dfac = - boundary_radius * dR / R**2
            bx = x * fac
            by = y * fac
            dbx = dx * fac + x * dfac
            dby = dy * fac + y * dfac
        # compute distance to boundary D and its time derivative dD:
        relx = bx - x
        rely = by - y
        drelx = dbx - dx
        drely = dby - dy
        D = np.sqrt(relx**2 + rely**2)
        dD = (relx*drelx + rely*drely) / D
        # compute relative angle to boundary theta and its time derivative:
        psi = np.arctan2(relx, rely)
        dpsi = (drelx*rely - relx*drely) / (rely**2 + relx**2)
        theta = psi - phi
        dtheta = dpsi - dphi
        sintheta = np.sin(theta)
        costheta = np.cos(theta)
        dsintheta = costheta * dtheta
        dcostheta = -sintheta * dtheta
        # field:
        fx, fy = fxfy(x, y, self._coeffs)
        dxfx, dyfx, dxfy, dyfy = jacobian(x, y, self._coeffs) 
        # store observation:
        self.obs = np.array([x, y, sinphi, cosphi, D, sintheta, costheta,
                            dx,dy,dsinphi,dcosphi,dD,dsintheta,dcostheta,
                            fx, fy, dxfx, dyfx, dxfy, dyfy])
        # store aux. data for rendering:
        self._bx, self._by = bx, by

    def _remember(self):
        self.history.append({
            't': self.t, 
            'state': self.state, 
            'action': self.action, 
            'reward': self.reward,
            'terminal': self.terminal,
            'obs': self.obs
            })
        

# aux func.:
    
def wrap(x, m, M):
    """Wraps ``x`` so m <= x <= M; but unlike ``bound()`` which
    truncates, ``wrap()`` wraps x around the coordinate system defined by m,M.\n
    For example, m = -180, M = 180 (degrees), x = 360 --> returns 0.

    Args:
        x: a scalar
        m: minimum possible value in range
        M: maximum possible value in range

    Returns:
        x: a scalar, wrapped
    """
    diff = M - m
    while x > M:
        x = x - diff
    while x < m:
        x = x + diff
    return x

