from __future__ import division
from lib.libmqc_qed import el_run
from mqc_qed.mqc import MQC_QED
from misc import eps, au_to_K, call_name, typewriter
import random, os, shutil, textwrap
import numpy as np
import pickle

class SH(MQC_QED):
    """ Class for surface hopping dynamics coupled to confined cavity mode

        :param object polariton: Polariton object
        :param object thermostat: Thermostat object
        :param integer istate: Initial state
        :param double dt: Time interval
        :param integer nsteps: Total step of nuclear propagation
        :param integer nesteps: Total step of electronic propagation
        :param string elec_object: Electronic equation of motions
        :param string propagator: Electronic propagator
        :param boolean l_print_dm: Logical to print population and coherence
        :param boolean l_adj_nac: Adjust nonadiabatic coupling to align the phases
        :param boolean l_adj_tdp: Adjust transition dipole moments to align the phases
        :param string hop_rescale: Velocity rescaling method after successful hop
        :param string hop_reject: Velocity rescaling method after frustrated hop
        :param init_coef: Initial coefficient
        :type init_coef: double, list or complex, list
        :param string dec_correction: Simple decoherence correction schemes
        :param double edc_parameter: Energy constant (H) for rescaling coefficients in edc
        :param string unit_dt: Unit of time step 
        :param integer out_freq: Frequency of printing output
        :param integer verbosity: Verbosity of output
    """
    def __init__(self, polariton, thermostat=None, istate=0, dt=0.5, nsteps=1000, nesteps=20, \
        elec_object="coefficient", propagator="rk4", l_print_dm=True, l_adj_nac=True, l_adj_tdp=True, \
        hop_rescale="augment", hop_reject="reverse", init_coef=None, dec_correction=None, \
        edc_parameter=0.1, unit_dt="fs", out_freq=1, verbosity=0):
        # Initialize input values
        super().__init__(polariton, thermostat, istate, dt, nsteps, nesteps, elec_object, \
            propagator, l_print_dm, l_adj_nac, l_adj_tdp, init_coef, unit_dt, out_freq, verbosity)

        # Initialize SH variables
        self.rstate = self.istate
        self.rstate_old = self.rstate

        self.rand = 0.
        self.prob = np.zeros(self.pol.pst)
        self.acc_prob = np.zeros(self.pol.pst + 1)

        self.l_hop = False
        self.l_reject = False

        self.hop_rescale = hop_rescale.lower()
        if not (self.hop_rescale in ["energy", "velocity", "momentum", "augment"]):
            error_message = "Invalid rescaling method for accepted hop!"
            error_vars = f"hop_rescale = {self.hop_rescale}"
            raise ValueError (f"( {self.md_type}.{call_name()} ) {error_message} ( {error_vars} )")

        self.hop_reject = hop_reject.lower()
        if not (self.hop_reject in ["keep", "reverse"]):
            error_message = "Invalid rescaling method for frustrated hop!"
            error_vars = f"hop_reject = {self.hop_reject}"
            raise ValueError (f"( {self.md_type}.{call_name()} ) {error_message} ( {error_vars} )")

        # Initialize decoherence variables
        self.dec_correction = dec_correction
        self.edc_parameter = edc_parameter

        if (self.dec_correction != None):
            self.dec_correction = self.dec_correction.lower()

        if not (self.dec_correction in [None, "idc", "edc"]):
            error_message = "Invalid decoherence corrections in FSSH method!"
            error_vars = f"dec_correction = {self.dec_correction}"
            raise ValueError (f"( {self.md_type}.{call_name()} ) {error_message} ( {error_vars} )")

        # Check error for incompatible cases
        if (self.pol.l_pnacme):
            # No polaritonic analytical nonadiabatic couplings exist
            if (self.hop_rescale in ["velocity", "momentum", "augment"]):
                error_message = "pNACVs are not available with current QED object, only isotropic rescaling is possible!"
                error_vars = f"hop_rescale = {self.hop_rescale}"
                raise ValueError (f"( {self.md_type}.{call_name()} ) {error_message} ( {error_vars} )")
            if (self.hop_reject == "reverse"):
                error_message = "pNACVs are not available with current QED object, only keep rescaling is possible!"
                error_vars = f"hop_reject = {self.hop_reject}"
                raise ValueError (f"( {self.md_type}.{call_name()} ) {error_message} ( {error_vars} )")

        # Debug variables
        self.dotpopnac_d = np.zeros(self.pol.pst)

        # Initialize event to print
        self.event = {"HOP": []}

    def run(self, qed, qm, mm=None, output_dir="./", l_save_qed_log=False, l_save_qm_log=False, \
        l_save_mm_log=False, l_save_scr=True, restart=None):
        """ Run MQC dynamics according to surface hopping dynamics

            :param object qed: QED object containing cavity-molecule interaction
            :param object qm: QM object containing on-the-fly calculation information
            :param object mm: MM object containing MM calculation information
            :param string output_dir: Name of directory where outputs to be saved.
            :param boolean l_save_qed_log: Logical for saving QED calculation log
            :param boolean l_save_qm_log: Logical for saving QM calculation log
            :param boolean l_save_mm_log: Logical for saving MM calculation log
            :param boolean l_save_scr: Logical for saving scratch directory
            :param string restart: Option for controlling dynamics restarting
        """
        # Initialize PyUNIxMD
        base_dir, unixmd_dir, qed_log_dir, qm_log_dir, mm_log_dir = \
            self.run_init(qed, qm, mm, output_dir, l_save_qed_log, l_save_qm_log, l_save_mm_log, l_save_scr, restart)
        bo_list = [ist for ist in range(self.pol.nst)]
        pol_list = [self.rstate]
        qm.calc_coupling = True
        qm.calc_tdp = True
        qm.calc_tdp_grad = False
        # Exact force needs transition dipole gradients
        if (qed.force_level == "full"):
            qm.calc_tdp_grad = True
        # FSSH needs to calculate pNACVs or pNACMEs
        qed.calc_coupling = True
        self.print_init(qed, qm, mm, restart)

        if (restart == None):
            # Calculate initial input geometry at t = 0.0 s
            self.istep = -1
            self.pol.reset_bo(qm.calc_coupling, qm.calc_tdp, qm.calc_tdp_grad)
            self.pol.reset_qed(qm.calc_coupling)

            qm.get_data(self.pol, base_dir, bo_list, self.dt, self.istep, calc_force_only=False)
            if (self.pol.l_qmmm and mm != None):
                mm.get_data(self.pol, base_dir, bo_list, self.istep, calc_force_only=False)
            if (not self.pol.l_nacme):
                self.pol.get_nacme()

            qed.get_data(self.pol, base_dir, pol_list, self.dt, self.istep, calc_force_only=False)
            if (not self.pol.l_pnacme):
                self.pol.get_pnacme()
            qed.transform(self.pol, mode="a2d")

            self.hop_prob(qed)
            self.hop_check(pol_list)
            self.evaluate_hop(qed, pol_list)

            if (self.dec_correction == "idc"):
                if (self.l_hop or self.l_reject):
                    self.correct_dec_idc()
                    qed.transform(self.pol, mode="a2d")
            elif (self.dec_correction == "edc"):
                # If kinetic is 0, coefficient/density matrix are update into itself
                if (self.pol.ekin_qm > eps):
                    self.correct_dec_edc()
                    qed.transform(self.pol, mode="a2d")

            if (self.l_hop):
                qed.get_data(self.pol, base_dir, pol_list, self.dt, self.istep, calc_force_only=True)

            self.update_energy()

            self.write_md_output(unixmd_dir, self.istep)
            self.print_step(self.istep)

        elif (restart == "write"):
            # Reset initial time step to t = 0.0 s
            self.istep = -1
            self.write_md_output(unixmd_dir, self.istep)
            self.print_step(self.istep)

        elif (restart == "append"):
            # Set initial time step to last successful step of previous dynamics
            self.istep = self.fstep

        self.istep += 1

        # Main MD loop
        for istep in range(self.istep, self.nsteps):

            self.calculate_force()
            self.cl_update_position()

            self.pol.backup_bo(qm.calc_coupling, qm.calc_tdp)
            qed.backup_qed()
            self.pol.reset_bo(qm.calc_coupling, qm.calc_tdp, qm.calc_tdp_grad)
            self.pol.reset_qed(qm.calc_coupling)

            qm.get_data(self.pol, base_dir, bo_list, self.dt, istep, calc_force_only=False)
            if (self.pol.l_qmmm and mm != None):
                mm.get_data(self.pol, base_dir, bo_list, istep, calc_force_only=False)

            if (not self.pol.l_nacme and self.l_adj_nac):
                self.pol.adjust_nac()
            if (self.l_adj_tdp):
                self.pol.adjust_tdp()
            qed.get_data(self.pol, base_dir, pol_list, self.dt, istep, calc_force_only=False)

            self.calculate_force()
            self.cl_update_velocity()

            if (not self.pol.l_nacme):
                self.pol.get_nacme()
            if (not self.pol.l_pnacme):
                self.pol.get_pnacme()
            else:
                qed.calculate_pnacme(self.pol)

            el_run(self, qed)
            qed.transform(self.pol, mode="d2a")

            self.hop_prob(qed)
            self.hop_check(pol_list)
            self.evaluate_hop(qed, pol_list)

            if (self.dec_correction == "idc"):
                if (self.l_hop or self.l_reject):
                    self.correct_dec_idc()
                    qed.transform(self.pol, mode="a2d")
            elif (self.dec_correction == "edc"):
                # If kinetic is 0, coefficient/density matrix are update into itself
                if (self.pol.ekin_qm > eps):
                    self.correct_dec_edc()
                    qed.transform(self.pol, mode="a2d")

            if (self.l_hop):
                qed.get_data(self.pol, base_dir, pol_list, self.dt, istep, calc_force_only=True)

            if (self.thermo != None):
                self.thermo.run(self, self.pol)

            self.update_energy()

            if ((istep + 1) % self.out_freq == 0):
                self.write_md_output(unixmd_dir, istep)
            if ((istep + 1) % self.out_freq == 0 or len(self.event["HOP"]) > 0):
                self.print_step(istep)
            if (istep == self.nsteps - 1):
                self.write_final_xyz(unixmd_dir, istep)

            self.fstep = istep
            restart_file = os.path.join(base_dir, "RESTART.bin")
            with open(restart_file, 'wb') as f:
                pickle.dump({'qed':qed, 'qm':qm, 'md':self}, f)

        # Delete scratch directory
        if (not l_save_scr):
            tmp_dir = os.path.join(unixmd_dir, "scr_qed")
            if (os.path.exists(tmp_dir)):
                shutil.rmtree(tmp_dir)

            tmp_dir = os.path.join(unixmd_dir, "scr_qm")
            if (os.path.exists(tmp_dir)):
                shutil.rmtree(tmp_dir)

            if (self.pol.l_qmmm and mm != None):
                tmp_dir = os.path.join(unixmd_dir, "scr_mm")
                if (os.path.exists(tmp_dir)):
                    shutil.rmtree(tmp_dir)

    def hop_prob(self, qed):
        """ Routine to calculate hopping probabilities

            :param object qed: QED object containing cavity-molecule interaction
        """
        # Reset surface hopping variables
        self.rstate_old = self.rstate

        self.prob = np.zeros(self.pol.pst)
        self.acc_prob = np.zeros(self.pol.pst + 1)

        self.l_hop = False

        accum = 0.

        # tmp_ham = U^+ * H * U
        tmp_ham = np.zeros((self.pol.pst, self.pol.pst)) 
        tmp_ham = np.matmul(np.transpose(qed.unitary), np.matmul(qed.ham_d, qed.unitary))
        # self.pol.pnacme = U^+ * K * U + U^+ * U_dot
        # H and K are Hamiltonian and NACME in uncoupled basis

        if (not qed.l_trivial):
            for ist in range(self.pol.pst):
                if (ist != self.rstate):
                    self.prob[ist] = - 2. * (self.pol.rho_a.imag[self.rstate, ist] * tmp_ham[self.rstate, ist] \
                        - self.pol.rho_a.real[self.rstate, ist] * self.pol.pnacme[self.rstate, ist]) \
                        * self.dt / self.pol.rho_a.real[self.rstate, self.rstate]

                    if (self.prob[ist] < 0.):
                        self.prob[ist] = 0.
                    accum += self.prob[ist]
                self.acc_prob[ist + 1] = accum
            psum = self.acc_prob[self.pol.pst]
        else:
            for ist in range(self.pol.pst):
                if (ist != self.rstate):
                    if (ist == qed.trivial_state):
                        self.prob[ist] = 1.
                    else:
                        self.prob[ist] = 0.

                    accum += self.prob[ist]
                self.acc_prob[ist + 1] = accum
            psum = self.acc_prob[self.pol.pst]

        if (psum > 1.):
            self.prob /= psum
            self.acc_prob /= psum

    def hop_check(self, pol_list):
        """ Routine to check hopping occurs with random number

            :param integer,list pol_list: List of polaritonic states for QED calculation
        """
        self.rand = random.random()
        for ist in range(self.pol.pst):
            if (ist == self.rstate):
                continue
            if (self.rand > self.acc_prob[ist] and self.rand <= self.acc_prob[ist + 1]):
                self.l_hop = True
                self.rstate = ist
                pol_list[0] = self.rstate

    def evaluate_hop(self, qed, pol_list):
        """ Routine to evaluate hopping and velocity rescaling

            :param object qed: QED object containing cavity-molecule interaction
            :param integer,list pol_list: List of polaritonic states for QED calculation
        """
        if (self.l_hop):
            if (not qed.l_trivial):
                # Calculate potential difference between hopping states
                pot_diff = self.pol.pol_states[self.rstate].energy - self.pol.pol_states[self.rstate_old].energy

                # Solve quadratic equation for scaling factor of velocities
                a = 1.
                b = 1.
                det = 1.
                if (self.hop_rescale == "velocity"):
                    a = np.sum(self.pol.mass[0:self.pol.nat_qm] * np.sum(self.pol.pnac[self.rstate_old, self.rstate] ** 2., axis=1))
                    b = 2. * np.sum(self.pol.mass[0:self.pol.nat_qm] * np.sum(self.pol.pnac[self.rstate_old, self.rstate] \
                        * self.pol.vel[0:self.pol.nat_qm], axis=1))
                    c = 2. * pot_diff
                    det = b ** 2. - 4. * a * c
                elif (self.hop_rescale == "momentum"):
                    a = np.sum(1. / self.pol.mass[0:self.pol.nat_qm] * np.sum(self.pol.pnac[self.rstate_old, self.rstate] ** 2., axis=1))
                    b = 2. * np.sum(np.sum(self.pol.pnac[self.rstate_old, self.rstate] * self.pol.vel[0:self.pol.nat_qm], axis=1))
                    c = 2. * pot_diff
                    det = b ** 2. - 4. * a * c
                elif (self.hop_rescale == "augment"):
                    a = np.sum(1. / self.pol.mass[0:self.pol.nat_qm] * np.sum(self.pol.pnac[self.rstate_old, self.rstate] ** 2., axis=1))
                    b = 2. * np.sum(np.sum(self.pol.pnac[self.rstate_old, self.rstate] * self.pol.vel[0:self.pol.nat_qm], axis=1))
                    c = 2. * pot_diff
                    det = b ** 2. - 4. * a * c

                # Default: hopping is allowed
                self.l_reject = False

                # Velocities cannot be adjusted when zero kinetic energy is given
                if (self.hop_rescale == "energy" and self.pol.ekin_qm < eps):
                    self.l_reject = True
                # Clasically forbidden hop due to lack of kinetic energy
                if (self.pol.ekin_qm < pot_diff):
                    self.l_reject = True
                # Kinetic energy is enough, but there is no solution for scaling factor
                if (det < 0.):
                    self.l_reject = True
                # When kinetic energy is enough, velocities are always rescaled in 'augment' case
                if (self.hop_rescale == "augment" and self.pol.ekin_qm > pot_diff):
                    self.l_reject = False

                if (self.l_reject):
                    # Record event for frustrated hop
                    if (self.pol.ekin_qm < pot_diff):
                        self.event["HOP"].append(f"Reject hopping: smaller kinetic energy than potential energy difference between {self.rstate} and {self.rstate_old}")
                    # Set scaling constant with respect to 'hop_reject'
                    if (self.hop_reject == "keep"):
                        self.event["HOP"].append("Reject hopping: no solution to find rescale factor, velocity is not changed")
                    elif (self.hop_reject == "reverse"):
                        # x = - 1 when 'hop_rescale' is 'energy', otherwise x = - b / a
                        self.event["HOP"].append("Reject hopping: no solution to find rescale factor, velocity is reversed along coupling direction")
                        x = - b / a
                    # Recover old running state
                    self.l_hop = False
                    self.rstate = self.rstate_old
                    pol_list[0] = self.rstate
                else:
                    if (self.hop_rescale == "energy" or (det < 0. and self.hop_rescale == "augment")):
                        if (det < 0.):
                            self.event["HOP"].append("Accept hopping: no solution to find rescale factor, but velocity is simply rescaled")
                        x = np.sqrt(1. - pot_diff / self.pol.ekin_qm)
                    else:
                        if (b < 0.):
                            x = 0.5 * (- b - np.sqrt(det)) / a
                        else:
                            x = 0.5 * (- b + np.sqrt(det)) / a

                # Rescale velocities for QM atoms
                if (not (self.hop_reject == "keep" and self.l_reject)):
                    if (self.hop_rescale == "energy"):
                        self.pol.vel[0:self.pol.nat_qm] *= x

                    elif (self.hop_rescale == "velocity"):
                        self.pol.vel[0:self.pol.nat_qm] += x * self.pol.pnac[self.rstate_old, self.rstate]

                    elif (self.hop_rescale == "momentum"):
                        self.pol.vel[0:self.pol.nat_qm] += x * self.pol.pnac[self.rstate_old, self.rstate] / \
                            self.pol.mass[0:self.pol.nat_qm].reshape((-1, 1))

                    elif (self.hop_rescale == "augment"):
                        if (det > 0. or self.pol.ekin_qm < pot_diff):
                            self.pol.vel[0:self.pol.nat_qm] += x * self.pol.pnac[self.rstate_old, self.rstate] / \
                                self.pol.mass[0:self.pol.nat_qm].reshape((-1, 1))
                        else:
                            self.pol.vel[0:self.pol.nat_qm] *= x

                # Update kinetic energy
                self.pol.update_kinetic()

        # Record hopping event
        if (self.rstate != self.rstate_old):
            if (not qed.l_trivial):
                self.event["HOP"].append(f"Accept hopping: hop {self.rstate_old} -> {self.rstate}")
            else:
                self.event["HOP"].append(f"Trivial crossing hopping: hop {self.rstate_old} -> {self.rstate}")

    def correct_dec_idc(self):
        """ Routine to decoherence correction, instantaneous decoherence correction(IDC) scheme
        """
        if (self.elec_object == "coefficient"):
            for states in self.pol.pol_states:
                states.coef_a = 0. + 0.j
            self.pol.pol_states[self.rstate].coef_a = 1. + 0.j

        self.pol.rho_a = np.zeros((self.pol.pst, self.pol.pst), dtype=np.complex128)
        self.pol.rho_a[self.rstate, self.rstate] = 1. + 0.j

    def correct_dec_edc(self):
        """ Routine to decoherence correction, energy-based decoherence correction(EDC) scheme
        """
        # Save exp(-dt/tau) instead of tau itself
        exp_tau = np.array([1. if (ist == self.rstate) else np.exp(- self.dt / ((1. + self.edc_parameter / self.pol.ekin_qm) / \
            np.abs(self.pol.pol_states[ist].energy - self.pol.pol_states[self.rstate].energy))) for ist in range(self.pol.pst)])
        rho_update = 1.

        if (self.elec_object == "coefficient"):
            # Update coefficients
            for ist in range(self.pol.pst):
                # self.pol.pol_states[self.rstate] need other updated coefficients
                if (ist != self.rstate):
                    self.pol.pol_states[ist].coef_a *= exp_tau[ist]
                    rho_update -= self.pol.pol_states[ist].coef_a.conjugate() * self.pol.pol_states[ist].coef_a

            self.pol.pol_states[self.rstate].coef_a *= np.sqrt(rho_update / self.pol.rho_a[self.rstate, self.rstate])

            # Get density matrix elements from coefficients
            for ist in range(self.pol.pst):
                for jst in range(ist, self.pol.pst):
                    self.pol.rho_a[ist, jst] = self.pol.pol_states[ist].coef_a.conjugate() * self.pol.pol_states[jst].coef_a
                    self.pol.rho_a[jst, ist] = self.pol.rho_a[ist, jst].conjugate()

#        elif (self.elec_object == "density"):
#            # save old running state element for update running state involved elements
#            rho_old_rstate = self.mol.rho[self.rstate, self.rstate]
#            for ist in range(self.mol.nst):
#                for jst in range(ist, self.mol.nst):
#                    # Update density matrix. self.mol.rho[ist, rstate] suffers half-update because exp_tau[rstate] = 1
#                    self.mol.rho[ist, jst] *= exp_tau[ist] * exp_tau[jst]
#                    self.mol.rho[jst, ist] = self.mol.rho[ist, jst].conjugate()
#
#                if (ist != self.rstate):
#                    # Update rho[self.rstate, self.rstate] by subtracting other diagonal elements
#                    rho_update -= self.mol.rho[ist, ist]
#
#            # Update rho[self.rstate, ist] and rho[ist, self.rstate] by using rho_update and rho_old_rstate
#            # rho[self.rstate, self.rstate] automatically update by double counting
#            for ist in range(self.mol.nst):
#                self.mol.rho[ist, self.rstate] *= np.sqrt(rho_update / rho_old_rstate)
#                self.mol.rho[self.rstate, ist] *= np.sqrt(rho_update / rho_old_rstate)

    def calculate_force(self):
        """ Routine to calculate the forces
        """
        self.rforce = np.copy(self.pol.pol_states[self.rstate].force)

    def update_energy(self):
        """ Routine to update the energy of molecules in surface hopping dynamics
        """
        # Update kinetic energy
        self.pol.update_kinetic()
        self.pol.epot = self.pol.pol_states[self.rstate].energy
        self.pol.etot = self.pol.epot + self.pol.ekin

    def write_md_output(self, unixmd_dir, istep):
        """ Write output files

            :param string unixmd_dir: PyUNIxMD directory
            :param integer istep: Current MD step
        """
        # Write the common part
        super().write_md_output(unixmd_dir, istep)

        # Write hopping-related quantities
        self.write_sh(unixmd_dir, istep)

        # Write time-derivative population
        self.write_dotpop(unixmd_dir, istep)

    def write_sh(self, unixmd_dir, istep):
        """ Write hopping-related quantities into files

            :param string unixmd_dir: PyUNIxMD directory
            :param integer istep: Current MD step
        """
        # Write SHSTATE file
        tmp = f'{istep + 1:9d}{"":14s}{self.rstate}'
        typewriter(tmp, unixmd_dir, "SHSTATE", "a")

        # Write SHPROB file
        tmp = f'{istep + 1:9d}' + "".join([f'{self.prob[ist]:15.8f}' for ist in range(self.pol.pst)])
        typewriter(tmp, unixmd_dir, "SHPROB", "a")

    def write_dotpop(self, unixmd_dir, istep):
        """ Write time-derivative population

            :param string unixmd_dir: PyUNIxMD directory
            :param integer istep: Current MD step
        """
        if (self.verbosity >= 1):
            # Write NAC term in DOTPOPNACD
            tmp = f'{istep + 1:9d}' + "".join([f'{pop:15.8f}' for pop in self.dotpopnac_d])
            typewriter(tmp, unixmd_dir, "DOTPOPNACD", "a")

    def print_init(self, qed, qm, mm, restart):
        """ Routine to print the initial information of dynamics

            :param object qed: QED object containing cavity-molecule interaction
            :param object qm: QM object containing on-the-fly calculation information
            :param object mm: MM object containing MM calculation information
            :param string restart: Option for controlling dynamics restarting
        """
        # Print initial information about polariton, qed, qm, mm and thermostat
        super().print_init(qed, qm, mm, restart)

        # Print dynamics information for start line
        dynamics_step_info = textwrap.dedent(f"""\

        {"-" * 118}
        {"Start Dynamics":>65s}
        {"-" * 118}
        """)

        # Print INIT for each step
        INIT = f" #INFO{'STEP':>8s}{'State':>7s}{'Kinetic(H)':>14s}{'Potential(H)':>15s}{'Total(H)':>13s}{'Temperature(K)':>17s}{'Norm.':>8s}"
        dynamics_step_info += INIT

        # Print DEBUG1 for each step
        if (self.verbosity >= 1):
            DEBUG1 = f" #DEBUG1{'STEP':>6s}{'Rand.':>11s}{'Acc. Hopping Prob.':>28s}"
            dynamics_step_info += "\n" + DEBUG1

        print (dynamics_step_info, flush=True)

    def print_step(self, istep):
        """ Routine to print each steps information about dynamics

            :param integer istep: Current MD step
        """
        ctemp = self.pol.ekin * 2. / float(self.pol.ndof) * au_to_K
        norm = 0.
        for ist in range(self.pol.pst):
            norm += self.pol.rho_a.real[ist, ist]

        # Print INFO for each step
        INFO = f" INFO{istep + 1:>9d}{self.rstate:>5d}"
        INFO += f"{self.pol.ekin:16.8f}{self.pol.epot:15.8f}{self.pol.etot:15.8f}"
        INFO += f"{ctemp:13.6f}"
        INFO += f"{norm:11.5f}"
        print (INFO, flush=True)

        # Print DEBUG1 for each step
        if (self.verbosity >= 1):
            DEBUG1 = f" DEBUG1{istep + 1:>7d}"
            DEBUG1 += f"{self.rand:11.5f}"
            for ist in range(self.pol.pst):
                DEBUG1 += f"{self.acc_prob[ist]:12.5f} ({self.rstate}->{ist})"
            print (DEBUG1, flush=True)

        # Print event in surface hopping
        for category, events in self.event.items():
            if (len(events) != 0):
                for ievent in events:
                    print (f" {category}{istep + 1:>9d}  {ievent}", flush=True)
        self.event["HOP"] = []


