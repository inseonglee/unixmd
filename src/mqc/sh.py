from __future__ import division
from build.el_propagator import el_run
from mqc.mqc import MQC
from misc import eps, au_to_K, call_name, typewriter
import random, os, shutil, textwrap
import numpy as np
import pickle
 
class SH(MQC):
    """ Class for surface hopping dynamics

        :param object molecule: molecule object
        :param object thermostat: thermostat type
        :param integer istate: initial adiabatic state
        :param double dt: time interval
        :param integer nsteps: nuclear step
        :param integer nesteps: electronic step
        :param string propagation: propagation scheme
        :param string solver: propagation solver
        :param boolean l_pop_print: logical to print BO population and coherence
        :param boolean l_adjnac: logical to adjust nonadiabatic coupling
        :param string vel_rescale: velocity rescaling method after successful hop
        :param string vel_reject: velocity rescaling method after frustrated hop
        :param coefficient: initial BO coefficient
        :type coefficient: double, list or complex, list
        :param string unit_dt: unit of time step (fs = femtosecond, au = atomic unit)
        :param integer out_freq: frequency of printing output
        :param integer verbosity: verbosity of output
    """
    def __init__(self, molecule, thermostat=None, istate=0, dt=0.5, nsteps=1000, nesteps=10000, \
        propagation="density", solver="rk4", l_pop_print=False, l_adjnac=True, vel_rescale="momentum", \
        vel_reject="reverse", coefficient=None, unit_dt="fs", out_freq=1, verbosity=0):
        # Initialize input values
        super().__init__(molecule, thermostat, istate, dt, nsteps, nesteps, \
            propagation, solver, l_pop_print, l_adjnac, coefficient, unit_dt, out_freq, verbosity)

        # Initialize SH variables
        self.rstate = istate
        self.rstate_old = self.rstate

        self.rand = 0.
        self.prob = np.zeros(self.mol.nst)
        self.acc_prob = np.zeros(self.mol.nst + 1)

        self.l_hop = False
        self.l_reject = False

        self.vel_rescale = vel_rescale
        if not (self.vel_rescale in ["energy", "velocity", "momentum", "augment"]): 
            raise ValueError (f"( {self.md_type}.{call_name()} ) Invalid 'vel_rescale'! {self.vel_rescale}")

        self.vel_reject = vel_reject
        if not (self.vel_reject in ["keep", "reverse"]): 
            raise ValueError (f"( {self.md_type}.{call_name()} ) Invalid 'vel_reject'! {self.vel_reject}")

        # Check error for incompatible cases
        if (self.mol.l_nacme): 
            # No analytical nonadiabatic couplings exist
            if (self.vel_rescale in ["velocity", "momentum", "augment"]): 
                raise ValueError (f"( {self.md_type}.{call_name()} ) Use 'energy' rescaling for 'vel_rescale'! {self.vel_rescale}")
            if (self.vel_reject == "reverse"):
                raise ValueError (f"( {self.md_type}.{call_name()} ) Use 'keep' rescaling for 'vel_reject'! {self.vel_reject}")

        # Initialize event to print
        self.event = {"HOP": []}

    def run(self, qm, mm=None, input_dir="./", save_QMlog=False, save_MMlog=False, save_scr=True, restart=None):
        """ Run MQC dynamics according to surface hopping dynamics

            :param object qm: qm object containing on-the-fly calculation infomation
            :param object mm: mm object containing MM calculation infomation
            :param string input_dir: location of input directory
            :param boolean save_QMlog: logical for saving QM calculation log
            :param boolean save_MMlog: logical for saving MM calculation log
            :param boolean save_scr: logical for saving scratch directory
        """
        # Check compatibility of variables for QM and MM calculation
        if ((self.mol.qmmm and mm == None) or (not self.mol.qmmm and mm != None)):
            raise ValueError (f"( {self.md_type}.{call_name()} ) Both self.mol.qmmm and mm object is necessary! {self.mol.qmmm} and {mm}")
        if (self.mol.qmmm and mm != None):
            self.check_qmmm(qm, mm)

        # Set directory information
        input_dir = os.path.expanduser(input_dir)
        base_dir = os.path.join(os.getcwd(), input_dir)
        unixmd_dir = os.path.join(base_dir, "md")
        QMlog_dir = os.path.join(base_dir, "QMlog")
        if (self.mol.qmmm and mm != None):
            MMlog_dir = os.path.join(base_dir, "MMlog")
        
        # Initialize UNI-xMD
        bo_list = [self.rstate]
        qm.calc_coupling = True
        
        # Check and make directories
        if (restart == "append"):
            if (not os.path.exists(unixmd_dir)):
                raise ValueError (f"( {self.md_type}.{call_name()} ) Directory to be appended for restart not found! {restart} and {unixmd_dir}")
            if (not os.path.exists(unixmd_dir) and save_QMlog):
                os.makedirs(QMlog_dir)
            if (self.mol.qmmm and mm != None):
                if (not os.path.exists(MMlog_dir) and save_MMlog):
                    os.makedirs(MMlog_dir)
        else:
            if (os.path.exists(unixmd_dir)):
                shutil.move(unixmd_dir, unixmd_dir + "_old_" + str(os.getpid()))
            os.makedirs(unixmd_dir)

            if (os.path.exists(QMlog_dir)):
                shutil.move(QMlog_dir, QMlog_dir + "_old_" + str(os.getpid()))
            if (save_QMlog):
                os.makedirs(QMlog_dir)

            if (self.mol.qmmm and mm != None):
                if (os.path.exists(MMlog_dir)):
                    shutil.move(MMlog_dir, MMlog_dir + "_old_" + str(os.getpid()))
                if (save_MMlog):
                    os.makedirs(MMlog_dir)
            
            self.touch_file(unixmd_dir)

        os.chdir(base_dir)
        self.print_init(qm, mm, debug)
        
        if (restart == None):
            # Calculate initial input geometry at t = 0.0 s
            self.istep = -1
            self.mol.reset_bo(qm.calc_coupling)
            qm.get_data(self.mol, base_dir, bo_list, self.dt, istep=self.istep, calc_force_only=False)
            if (self.mol.qmmm and mm != None):
                mm.get_data(self.mol, base_dir, bo_list, istep=self.istep, calc_force_only=False)
            if (not self.mol.l_nacme):
                self.mol.get_nacme()

            self.hop_prob(istep=self.istep)
            self.hop_check(bo_list)
            self.evaluate_hop(bo_list, istep=self.istep)
            if (qm.re_calc and self.l_hop):
                qm.get_data(self.mol, base_dir, bo_list, self.dt, istep=self.istep, calc_force_only=True)
                if (self.mol.qmmm and mm != None):
                    mm.get_data(self.mol, base_dir, bo_list, istep=self.istep, calc_force_only=True)

            self.update_energy()

            self.write_md_output(unixmd_dir, istep=self.istep)
            self.print_step(debug, istep=self.istep)
        
        elif (restart == "write"):
            self.istep = -1
            self.write_md_output(unixmd_dir, istep=self.istep)
            self.print_step(debug, istep=self.istep)

        else:
            self.istep = self.fstep

        self.istep += 1

        # Main MD loop
        for istep in range(self.istep, self.nsteps):

            self.cl_update_position()

            self.mol.backup_bo()
            self.mol.reset_bo(qm.calc_coupling)
            qm.get_data(self.mol, base_dir, bo_list, self.dt, istep=istep, calc_force_only=False)
            if (self.mol.qmmm and mm != None):
                mm.get_data(self.mol, base_dir, bo_list, istep=istep, calc_force_only=False)

            if (not self.mol.l_nacme):
                self.mol.adjust_nac()

            self.cl_update_velocity()

            if (not self.mol.l_nacme):
                self.mol.get_nacme()

            el_run(self)

            self.hop_prob(istep=istep)
            self.hop_check(bo_list)
            self.evaluate_hop(bo_list, istep=istep)
            if (qm.re_calc and self.l_hop):
                qm.get_data(self.mol, base_dir, bo_list, self.dt, istep=istep, calc_force_only=True)
                if (self.mol.qmmm and mm != None):
                    mm.get_data(self.mol, base_dir, bo_list, istep=istep, calc_force_only=True)

            if (self.thermo != None):
                self.thermo.run(self)

            self.update_energy()

            if ((istep + 1) % self.out_freq == 0):
                self.write_md_output(unixmd_dir, istep=istep)
            if ((istep + 1) % self.out_freq == 0 or len(self.event["HOP"]) > 0):
                self.print_step(istep=istep)
            if (istep == self.nsteps - 1):
                self.write_final_xyz(unixmd_dir, istep=istep)

            self.fstep = istep
            restart_file = os.path.join(base_dir, "RESTART.bin")
            with open(restart_file, 'wb') as f:
                pickle.dump({'qm':qm, 'md':self}, f)

        # Delete scratch directory
        if (not save_scr):
            tmp_dir = os.path.join(unixmd_dir, "scr_qm")
            if (os.path.exists(tmp_dir)):
                shutil.rmtree(tmp_dir)

            if (self.mol.qmmm and mm != None):
                tmp_dir = os.path.join(unixmd_dir, "scr_mm")
                if (os.path.exists(tmp_dir)):
                    shutil.rmtree(tmp_dir)

    def hop_prob(self, istep):
        """ Routine to calculate hopping probabilities

            :param integer istep: current MD step
        """
        # Reset surface hopping variables
        self.rstate_old = self.rstate

        self.prob = np.zeros(self.mol.nst)
        self.acc_prob = np.zeros(self.mol.nst + 1)

        self.l_hop = False

        accum = 0.

        for ist in range(self.mol.nst):
            if (ist != self.rstate):
                self.prob[ist] = - 2. * self.mol.rho.real[ist, self.rstate] * \
                    self.mol.nacme[ist, self.rstate] * self.dt / self.mol.rho.real[self.rstate, self.rstate]

                if (self.prob[ist] < 0.):
                    self.prob[ist] = 0.
                accum += self.prob[ist]
            self.acc_prob[ist + 1] = accum
        psum = self.acc_prob[self.mol.nst]
 
        if (psum > 1.):
            self.prob /= psum
            self.acc_prob /= psum

    def hop_check(self, bo_list):
        """ Routine to check hopping occurs with random number

            :param integer,list bo_list: list of BO states for BO calculation
        """
        self.rand = random.random()
        for ist in range(self.mol.nst):
            if (ist == self.rstate):
                continue
            if (self.rand > self.acc_prob[ist] and self.rand <= self.acc_prob[ist + 1]):
                self.l_hop = True
                self.rstate = ist
                bo_list[0] = self.rstate

    def evaluate_hop(self, bo_list, istep):
        """ Routine to evaluate hopping and velocity rescaling

            :param integer,list bo_list: list of BO states for BO calculation
            :param integer istep: current MD step
        """
        if (self.l_hop):
            # Calculate potential difference between hopping states
            pot_diff = self.mol.states[self.rstate].energy - self.mol.states[self.rstate_old].energy

            # Solve quadratic equation for scaling factor of velocities
            a = 1.
            b = 1.
            det = 1.
            if (self.vel_rescale == "velocity"):
                a = np.sum(self.mol.mass * np.sum(self.mol.nac[self.rstate_old, self.rstate] ** 2., axis=1))
                b = 2. * np.sum(self.mol.mass * np.sum(self.mol.nac[self.rstate_old, self.rstate] * self.mol.vel, axis=1))
                c = 2. * pot_diff
                det = b ** 2. - 4. * a * c
            elif (self.vel_rescale == "momentum"):
                a = np.sum(1. / self.mol.mass * np.sum(self.mol.nac[self.rstate_old, self.rstate] ** 2., axis=1))
                b = 2. * np.sum(np.sum(self.mol.nac[self.rstate_old, self.rstate] * self.mol.vel, axis=1))
                c = 2. * pot_diff
                det = b ** 2. - 4. * a * c
            elif (self.vel_rescale == "augment"):
                a = np.sum(1. / self.mol.mass * np.sum(self.mol.nac[self.rstate_old, self.rstate] ** 2., axis=1))
                b = 2. * np.sum(np.sum(self.mol.nac[self.rstate_old, self.rstate] * self.mol.vel, axis=1))
                c = 2. * pot_diff
                det = b ** 2. - 4. * a * c

            # Default: hopping is allowed
            self.l_reject = False

            # Velocities cannot be adjusted when zero kinetic energy is given
            if (self.vel_rescale == "energy" and self.mol.ekin_qm < eps):
                self.l_reject = True
            # Clasically forbidden hop due to lack of kinetic energy
            if (self.mol.ekin_qm < pot_diff):
                self.l_reject = True
            # Kinetic energy is enough, but there is no solution for scaling factor
            if (det < 0.):
                self.l_reject = True
            # When kinetic energy is enough, velocities are always rescaled in 'augment' case
            if (self.vel_rescale == "augment" and self.mol.ekin_qm > pot_diff):
                self.l_reject = False

            if (self.l_reject):
                # Record event for frustrated hop
                if (self.mol.ekin_qm < pot_diff):
                    self.event["HOP"].append(f"Reject hopping: smaller kinetic energy than potential energy difference between {self.rstate} and {self.rstate_old}")
                # Set scaling constant with respect to 'vel_reject'
                if (self.vel_reject == "keep"):
                    self.event["HOP"].append("Reject hopping: no solution to find rescale factor, velocity is not changed")
                elif (self.vel_reject == "reverse"):
                    # x = - 1 when 'vel_rescale' is 'energy', otherwise x = - b / a
                    self.event["HOP"].append("Reject hopping: no solution to find rescale factor, velocity is reversed along coupling direction")
                    x = - b / a
                # Recover old running state
                self.l_hop = False
                self.rstate = self.rstate_old
                bo_list[0] = self.rstate
            else:
                if (self.vel_rescale == "energy" or (det < 0. and self.vel_rescale == "augment")):
                    if (det < 0.):
                        self.event["HOP"].append("Accept hopping: no solution to find rescale factor, but velocity is simply rescaled")
                    x = np.sqrt(1. - pot_diff / self.mol.ekin_qm)
                else:
                    if (b < 0.):
                        x = 0.5 * (- b - np.sqrt(det)) / a
                    else:
                        x = 0.5 * (- b + np.sqrt(det)) / a

            # Rescale velocities for QM atoms
            if (not (self.vel_reject == "keep" and self.l_reject)):
                if (self.vel_rescale == "energy"):
                    self.mol.vel[0:self.mol.nat_qm] *= x

                elif (self.vel_rescale == "velocity"):
                    self.mol.vel[0:self.mol.nat_qm] += x * self.mol.nac[self.rstate_old, self.rstate, 0:self.mol.nat_qm]

                elif (self.vel_rescale == "momentum"):
                    self.mol.vel[0:self.mol.nat_qm] += x * self.mol.nac[self.rstate_old, self.rstate, 0:self.mol.nat_qm] / \
                        self.mol.mass[0:self.mol.nat_qm].reshape((-1, 1))

                elif (self.vel_rescale == "augment"):
                    if (det > 0. or self.mol.ekin_qm < pot_diff):
                        self.mol.vel[0:self.mol.nat_qm] += x * self.mol.nac[self.rstate_old, self.rstate, 0:self.mol.nat_qm] / \
                            self.mol.mass[0:self.mol.nat_qm].reshape((-1, 1))
                    else:
                        self.mol.vel[0:self.mol.nat_qm] *= x

            # Update kinetic energy
            self.mol.update_kinetic()

        # Record hopping event
        if (self.rstate != self.rstate_old):
            self.event["HOP"].append(f"Accept hopping: hop {self.rstate_old} -> {self.rstate}")

    def calculate_force(self):
        """ Routine to calculate the forces
        """
        self.rforce = np.copy(self.mol.states[self.rstate].force)

    def update_energy(self):
        """ Routine to update the energy of molecules in surface hopping dynamics
        """
        # Update kinetic energy
        self.mol.update_kinetic()
        self.mol.epot = self.mol.states[self.rstate].energy
        self.mol.etot = self.mol.epot + self.mol.ekin

    def write_md_output(self, unixmd_dir, istep):
        """ Write output files

            :param string unixmd_dir: unixmd directory
            :param integer istep: current MD step
        """
        # Write the common part
        super().write_md_output(unixmd_dir, istep)

        # Write hopping-related quantities
        self.write_sh(unixmd_dir, istep)

    def write_sh(self, unixmd_dir, istep):
        """ Write hopping-related quantities into files

            :param string unixmd_dir: unixmd directory
            :param integer istep: current MD step
        """
        # Write SHSTATE file
        tmp = f'{istep + 1:9d}{"":14s}{self.rstate}'
        typewriter(tmp, unixmd_dir, "SHSTATE", "a")

        # Write SHPROB file
        tmp = f'{istep + 1:9d}' + "".join([f'{self.prob[ist]:15.8f}' for ist in range(self.mol.nst)])
        typewriter(tmp, unixmd_dir, "SHPROB", "a")

    def print_init(self, qm, mm):
        """ Routine to print the initial information of dynamics

            :param object qm: qm object containing on-the-fly calculation infomation
            :param object mm: mm object containing MM calculation infomation
        """
        # Print initial information about molecule, qm, mm and thermostat
        super().print_init(qm, mm)

        # Print dynamics information for start line
        dynamics_step_info = textwrap.dedent(f"""\

        {"-" * 118}
        {"Start Dynamics":>65s}
        {"-" * 118}
        """)

        # Print INIT for each step
        INIT = f" #INFO{'STEP':>8s}{'State':>7s}{'Max. Prob.':>14s}{'Rand.':>12s}{'Kinetic(H)':>15s}{'Potential(H)':>15s}{'Total(H)':>13s}{'Temperature(K)':>17s}{'Norm.':>8s}"
        dynamics_step_info += INIT

        # Print DEBUG1 for each step
        if (self.verbosity >= 1):
            DEBUG1 = f" #DEBUG1{'STEP':>6s}"
            for ist in range(self.mol.nst):
                DEBUG1 += f"{'Potential_':>14s}{ist}(H)"
            dynamics_step_info += "\n" + DEBUG1

        # Print DEBUG2 for each step
        if (self.verbosity >= 2):
            DEBUG2 = f" #DEBUG2{'STEP':>6s}{'Acc. Hopping Prob.':>22s}"
            dynamics_step_info += "\n" + DEBUG2

        print (dynamics_step_info, flush=True)

    def print_step(self, istep):
        """ Routine to print each steps infomation about dynamics

            :param integer istep: current MD step
        """
        if (istep == -1):
            max_prob = 0.
            hstate = self.rstate
        else:
            max_prob = max(self.prob)
            hstate = np.where(self.prob == max_prob)[0][0]

        ctemp = self.mol.ekin * 2. / float(self.mol.dof) * au_to_K
        norm = 0.
        for ist in range(self.mol.nst):
            norm += self.mol.rho.real[ist, ist]

        # Print INFO for each step
        INFO = f" INFO{istep + 1:>9d}{self.rstate:>5d}{max_prob:11.5f} ({self.rstate}->{hstate}){self.rand:11.5f}"
        INFO += f"{self.mol.ekin:14.8f}{self.mol.epot:15.8f}{self.mol.etot:15.8f}"
        INFO += f"{ctemp:13.6f}"
        INFO += f"{norm:11.5f}"
        print (INFO, flush=True)

        # Print DEBUG1 for each step
        if (self.verbosity >= 1):
            DEBUG1 = f" DEBUG1{istep + 1:>7d}"
            for ist in range(self.mol.nst):
                DEBUG1 += f"{self.mol.states[ist].energy:17.8f} "
            print (DEBUG1, flush=True)

        # Print DEBUG2 for each step
        if (self.verbosity >= 2):
            DEBUG2 = f" DEBUG2{istep + 1:>7d}"
            for ist in range(self.mol.nst):
                DEBUG2 += f"{self.acc_prob[ist]:12.5f} ({self.rstate}->{ist})"
            print (DEBUG2, flush=True)

        # Print event in surface hopping
        for category, events in self.event.items():
            if (len(events) != 0):
                for ievent in events:
                    print (f" {category}{istep + 1:>9d}  {ievent}", flush=True)
        self.event["HOP"] = []

