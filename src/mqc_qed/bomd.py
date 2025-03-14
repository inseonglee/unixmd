from __future__ import division
from mqc_qed.mqc import MQC_QED
from misc import au_to_K, call_name
import os, shutil, textwrap
import numpy as np
import pickle

class BOMD(MQC_QED):
    """ Class for born-oppenheimer molecular dynamics (BOMD) coupled to confined cavity mode

        :param object polariton: Polariton object
        :param object thermostat: Thermostat object
        :param integer istate: Initial state
        :param double dt: Time interval
        :param integer nsteps: Total step of nuclear propagation
        :param boolean l_adj_nac: Adjust nonadiabatic coupling to align the phases
        :param boolean l_adj_tdp: Adjust transition dipole moments to align the phases
        :param string unit_dt: Unit of time step
        :param integer out_freq: Frequency of printing output
        :param integer verbosity: Verbosity of output
    """
    def __init__(self, polariton, thermostat=None, istate=0, dt=0.5, nsteps=1000, l_adj_nac=True, \
        l_adj_tdp=True, unit_dt="fs", out_freq=1, verbosity=0):
        # Initialize input values
        super().__init__(polariton, thermostat, istate, dt, nsteps, None, None, None, \
            False, l_adj_nac, l_adj_tdp, None, unit_dt, out_freq, verbosity)

        # Initialize SH variables
        self.rstate = self.istate
        self.rstate_old = self.rstate
        self.l_hop = False

        # Initialize event to print
        self.event = {"HOP": []}

    def run(self, qed, qm, mm=None, output_dir="./", l_save_qed_log=False, l_save_qm_log=False, \
        l_save_mm_log=False, l_save_scr=True, restart=None):
        """ Run MQC dynamics according to BOMD

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
        qm.calc_coupling = False
        # Hellmann-Feynman force needs NACVs
        if (qed.force_level == "hf"):
            qm.calc_coupling = True
        qm.calc_tdp = True
        qm.calc_tdp_grad = False
        # Exact force needs transition dipole gradients
        if (qed.force_level == "full"):
            qm.calc_tdp_grad = True
        # BOMD does not need to calculate pNACVs or pNACMEs
        qed.calc_coupling = False
        self.print_init(qed, qm, mm, restart)

        if (restart == None):
            # Calculate initial input geometry at t = 0.0 s
            self.istep = -1
            self.pol.reset_bo(qm.calc_coupling, qm.calc_tdp, qm.calc_tdp_grad)
            self.pol.reset_qed(qm.calc_coupling)

            qm.get_data(self.pol, base_dir, bo_list, self.dt, self.istep, calc_force_only=False)
            if (self.pol.l_qmmm and mm != None):
                mm.get_data(self.pol, base_dir, bo_list, self.istep, calc_force_only=False)
            qed.get_data(self.pol, base_dir, pol_list, self.dt, self.istep, calc_force_only=False)

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

            if (qm.calc_coupling and not self.pol.l_nacme and self.l_adj_nac):
                self.pol.adjust_nac()
            if (self.l_adj_tdp):
                self.pol.adjust_tdp()
            qed.get_data(self.pol, base_dir, pol_list, self.dt, istep, calc_force_only=False)

            self.calculate_force()
            self.cl_update_velocity()

            self.trivial_hop(qed, pol_list)

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

    def trivial_hop(self, qed, pol_list):
        """ Routine to check trivial crossing between adjacent adiabatic states

            :param object qed: QED object containing cavity-molecule interaction
            :param integer,list pol_list: List of polaritonic states for QED calculation
        """
        # Reset surface hopping variables
        self.rstate_old = self.rstate
        self.l_hop = False

        if (qed.l_trivial):
            self.l_hop = True
            self.rstate = qed.trivial_state
            pol_list[0] = self.rstate

        # Record hopping event
        if (self.rstate != self.rstate_old):
            self.event["HOP"].append(f"Trivial crossing hopping: hop {self.rstate_old} -> {self.rstate}")

    def calculate_force(self):
        """ Routine to calculate the forces
        """
        self.rforce = np.copy(self.pol.pol_states[self.rstate].force)

    def update_energy(self):
        """ Routine to update the energy of molecules in BOMD
        """
        # Update kinetic energy
        self.pol.update_kinetic()
        self.pol.epot = self.pol.pol_states[self.rstate].energy
        self.pol.etot = self.pol.epot + self.pol.ekin

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
        INIT = f" #INFO{'STEP':>8s}{'State':>7s}{'Kinetic(H)':>13s}{'Potential(H)':>15s}{'Total(H)':>13s}{'Temperature(K)':>17s}"
        dynamics_step_info += INIT

        print (dynamics_step_info, flush=True)

    def print_step(self, istep):
        """ Routine to print each steps information about dynamics

            :param integer istep: Current MD step
        """
        ctemp = self.pol.ekin * 2. / float(self.pol.ndof) * au_to_K

        # Print INFO for each step
        INFO = f" INFO{istep + 1:>9d}{self.rstate:>5d} "
        INFO += f"{self.pol.ekin:14.8f}{self.pol.epot:15.8f}{self.pol.etot:15.8f}"
        INFO += f"{ctemp:13.6f}"
        print (INFO, flush=True)

        # Print event in surface hopping
        for category, events in self.event.items():
            if (len(events) != 0):
                for ievent in events:
                    print (f" {category}{istep + 1:>9d}  {ievent}", flush=True)
        self.event["HOP"] = []


