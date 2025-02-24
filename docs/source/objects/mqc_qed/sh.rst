
Surface Hopping
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Surface hopping dynamics, often called as Tully's fewest switches surface hopping dynamics (FSSH) is one of the most popular MQC methods.
It was introduced by Tully, J. C. in 1990 :cite:`Tully1990`, and has been augmented in various ways so far. The propagation of electrons and nuclei in cQED is done as follows.

.. math::

   M_{\nu}\ddot{\mathbf{R}}^{(I)}_{\nu}(t) = -\nabla_{\nu}E^{(I)}_{r}(t),

.. math::

   \dot{D}^{(I)}_{\beta}(t) = - \sum_{\alpha} \left[ {{i}\over{\hbar}} H^{(I)}_{\beta\alpha}(t) +
   \sum_{\nu} \mathbf{d}^{(I)}_{\beta\alpha,\nu} \cdot \dot{\bf R}^{(I)}_{\nu}(t) \right] D^{(I)}_{\alpha}(t)

The electronic propagation is still an Ehrenfest-type evolution, but the nuclei follow a *fixed* polaritonic potential energy surface denoted by :math:`E^{(I)}_{r}(t)`. The corresponding state is called a running state (force state).
The running state is chosen probabilistically at every MD step. The probabilities governing this process are called hopping probabilities naturally depending on the adiabatic population and the nonadiabatic couplings:

.. math::

   P^{(I)}_{K{\rightarrow}J}[t,t+{\Delta}t] = \Re[\rho^{(I)}_{KJ}(t)]
   \left[ \sum_{\alpha\beta} U^K_{\beta} \left( \sum_{\nu} \mathbf{d}^{(I)}_{\beta\alpha,\nu} \cdot \dot{\bf R}^{(I)}_{\nu}(t) \right) U^J_{\alpha}
   + \sum_{\alpha} U^K_{\alpha} \dot{U}^J_{\alpha} \right]
   {{2{\Delta}t} \over {\rho^{(I)}_{KK}(t)}}, \rho^{(I)}_{KJ}(t)=C^{(I)\ast}_K(t) C^{(I)}_J(t)

:math:`{\rho}(t)` represents the polaritonic density matrix. In this algorithm, the hopping probabilities
from the "current" running state to the others are considered and a random number is called to select the next
running state. If the coupling with an adiabatic state is strong enough, the probability will increase, so the running state is likely to transit to that state.

In :class:`SH` class, two ad hoc decoherence correction schemes are implemented.
One is instantaneous decoherence correction (IDC).
In the IDC algorithm, the polaritonic state immediately collapses to a running state whenever a hop occurs or is rejected.
The other is energy-based decoherence correction (EDC) :cite:`Granucci2010` which rescales polaritonic state coefficients based on the running state :math:`r` and energies of a target system.

+----------------------------+--------------------------------------------------+------------------+
| Parameters                 | Work                                             | Default          |
+============================+==================================================+==================+
| **polariton**              | Polariton object                                 |                  |
| (:class:`Polariton`)       |                                                  |                  |
+----------------------------+--------------------------------------------------+------------------+
| **thermostat**             | Thermostat object                                | *None*           |
| (:class:`Thermostat`)      |                                                  |                  |
+----------------------------+--------------------------------------------------+------------------+
| **istate**                 | Initial state                                    | *0*              |
| *(integer)*                |                                                  |                  |
+----------------------------+--------------------------------------------------+------------------+
| **dt**                     | Time interval                                    | *0.5*            |
| *(double)*                 |                                                  |                  |
+----------------------------+--------------------------------------------------+------------------+
| **nsteps**                 | Total step of nuclear propagation                | *1000*           |
| *(integer)*                |                                                  |                  |
+----------------------------+--------------------------------------------------+------------------+
| **nesteps**                | Total step of electronic propagation             | *20*             |
| *(integer)*                |                                                  |                  |
+----------------------------+--------------------------------------------------+------------------+
| **elec_object**            | Electronic equation of motions                   | *'coefficient'*  |
| *(string)*                 |                                                  |                  |
+----------------------------+--------------------------------------------------+------------------+
| **propagator**             | Electronic propagator                            | *'rk4'*          |
| *(string)*                 |                                                  |                  |
+----------------------------+--------------------------------------------------+------------------+
| **l_print_dm**             | Logical to print population and coherence        | *True*           |
| *(boolean)*                |                                                  |                  |
+----------------------------+--------------------------------------------------+------------------+
| **l_adj_nac**              | Adjust nonadiabatic coupling to align the phases | *True*           |
| *(boolean)*                |                                                  |                  |
+----------------------------+--------------------------------------------------+------------------+
| **l_adj_tdp**              | Adjust transition dipole moments to align        | *True*           |
| *(boolean)*                | the phases                                       |                  |
+----------------------------+--------------------------------------------------+------------------+
| **hop_rescale**            | Velocity rescaling method after successful hop   | *'augment'*      |
| *(string)*                 |                                                  |                  |
+----------------------------+--------------------------------------------------+------------------+
| **hop_reject**             | Velocity rescaling method after frustrated hop   | *'reverse'*      |
| *(string)*                 |                                                  |                  |
+----------------------------+--------------------------------------------------+------------------+
| **init_coef**              | Initial coefficient                              | *None*           |
| *(double/complex, list)*   |                                                  |                  |
+----------------------------+--------------------------------------------------+------------------+
| **dec_correction**         | Simple decoherence correction schemes            | *None*           |
| *(string)*                 |                                                  |                  |
+----------------------------+--------------------------------------------------+------------------+
| **edc_parameter**          | Energy constant (H) for rescaling coefficients   | *0.1*            |
| *(double)*                 | in edc                                           |                  |
+----------------------------+--------------------------------------------------+------------------+
| **unit_dt**                | Unit of time interval                            | *'fs'*           |
| *(string)*                 |                                                  |                  |
+----------------------------+--------------------------------------------------+------------------+
| **out_freq**               | Frequency of printing output                     | *1*              |
| *(integer)*                |                                                  |                  |
+----------------------------+--------------------------------------------------+------------------+
| **verbosity**              | Verbosity of output                              | *0*              | 
| *(integer)*                |                                                  |                  |
+----------------------------+--------------------------------------------------+------------------+


Detailed description of the parameters
""""""""""""""""""""""""""""""""""""""""""

- **istate** *(integer)* - Default: *0* (Ground state)
  
  This parameter specifies the initial running state. The possible range is from *0* to ``polariton.pst - 1``.
   
\

- **dt** *(double)* - Default: *0.5*
  
  This parameter determines the time interval of the nuclear time steps.
  You can select the unit of time for the dynamics with the **unit_dt** parameter.

\

- **nsteps** *(integer)* - Default: *1000*

  This parameter determines the total number of the nuclear time steps.

\

- **nesteps** *(integer)* - Default: *20*
  
  This parameter determines the number of electronic time steps between one nuclear time step for the integration of the electronic equation of motion.
  The electronic equation of motion is more sensitive to the time interval than the nuclear equation of motion since the electrons are much lighter than the nuclei.
  Therefore, the nuclear time step is further divided and electronic equation of motion is integrated with smaller time step.

\

- **elec_object** *(string)*- Default: *'coefficient'*
  
  The **elec_object** parameter determines the representation for the electrons
   
  + *'coefficient'*: Propagates the coefficients, i.e., :math:`\{D_{\beta}^{(I)}(t)\}`

\

- **propagator** *(string)* - Default: *'rk4'*

  This parameter determines the numerical integration method for the electronic equation of motion.

  + *'rk4'*: Integrates the coefficients using Runge-Kutta 4th order method.
  + *'exponential'*: Integrates the coefficients using exponential operator.
    In general, *'exponential'* is recommended for polariton dynamics.

\

- **l_print_dm** *(boolean)* - Default: *True*
  
  This parameter determines whether to write output files for the density matrix elements ('QEDPOPA', 'QEDCOHA', 'QEDPOPD', 'QEDCOHD') or not.
  If this option is set to *True*, then the 'QEDPOPA', 'QEDCOHA', 'QEDPOPD', and 'QEDCOHD' files are written during the dynamics.
  This option is effective only if the **elec_object** parameter is set to *'coefficient'* or ignored otherwise.

\

- **l_adj_nac** *(boolean)* - Default: *True* 

  If this parameter is set to *True*, the signs of the NACVs are adjusted to match the phases to the previous time step during the dynamics.

\

- **l_adj_tdp** *(boolean)* - Default: *True* 

  If this parameter is set to *True*, the signs of the TDPs are adjusted to match the phases to the previous time step during the dynamics.

\

- **hop_rescale** *(string)* - Default: *'augment'*

  This parameter determines the direction of the momentum to be adjusted after a hop to conserve the total energy.
  If there is not enough kinetic energy in this direction, the hop is rejected and the running state is switched back to the original state.
  
  + *'energy'*: Simply rescale the nuclear velocities.
  + *'momentum'*: Adjust the momentum in the direction of the pNACV.
  + *'augment'*: First, the hop is evaluated as the *'momentum'*. 
    If the kinetic energy is not enough, then the hop is evaluated again as the *'energy'*. 

\
   
- **hop_reject** *(string)* - Default: *'reverse'*
  
  This parameter determines the momentum rescaling method when a hop is rejected.
  
  + *'keep'*: Do nothing, keeps the nuclear velocities.
  + *'reverse'*: Reverse the momentum along the pNACV.

\

- **init_coef** *(double/complex, list)* - Default: *None*

  This parameter defines the initial polaritonic state coefficients.
  The elements can be either real or complex values.
  The length of this paramter should be same to ``polariton.pst``.
  If the parameter is not given, the coefficient and the density matrix are initialized according to the initial running state.

\

- **dec_correction** *(string)* - Default: *None*

  This parameter determines the simple decoherence correction method.

  + *'edc'*: Energy based decoherence correction (EDC) scheme of Granucci et al :cite:`Granucci2010`. 
  + *'idc'*: Instantaneous decoherence correction scheme.

\

- **edc_parameter** *(double)* - Default: *0.1*

  This parameter defines the energy parameter in the EDC equation in unit of H.

\

- **unit_dt** *(string)* - Default: *'fs'*

  This parameter determines the unit of time for the simulation.
  
  + *'fs'*: Femtosecond
  + *'au'*: Atomic unit

\

- **out_freq** *(integer)* - Default: *1*
  
  PyUNIxMD prints and writes the dynamics information at every **out_freq** time step.

\

- **verbosity** *(integer)* - Default: *0*

  This parameter determines the verbosity of the output files and stream.

  + **verbosity** :math:`\geq` *1*: Prints accumulated hopping probabilities and random numbers,
    and writes Ehrenfest term in time-derivative of populations to DOTPOPNACD.
  + **verbosity** :math:`\geq` *2*: Writes the pNACVs ('PNACV\_\ :math:`I`\_\ :math:`J`').

