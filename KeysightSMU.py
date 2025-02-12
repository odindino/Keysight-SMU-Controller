"""
Keysight B2902B SMU Advanced Control Library

This library provides comprehensive control for the Keysight B2902B SMU,
including basic operations, continuous monitoring, and automated measurements
for semiconductor device characterization.

Author: Your Name
Version: 2.0.0
Date: 2024-02-12
"""

import pyvisa
import time
import logging
import numpy as np
from typing import Optional, Tuple, Union, List, Dict
from enum import Enum
import pandas as pd
from datetime import datetime

class Channel(Enum):
    """SMU channel enumeration"""
    CH1 = 1
    CH2 = 2

class OutputMode(Enum):
    """Output mode enumeration"""
    VOLTAGE = 'VOLT'
    CURRENT = 'CURR'
    
class MeasurementQuality(Enum):
    """Measurement quality settings"""
    SHORT = 'SHORT'
    NORMAL = 'NORMAL'
    MEDIUM = 'MEDIUM'
    LONG = 'LONG'
    CUSTOM = 'CUSTOM'

class QualitySettings:
    """Quality settings for different measurement modes"""
    SETTINGS = {
        MeasurementQuality.SHORT: {'nplc': 0.1, 'samples': 1},
        MeasurementQuality.NORMAL: {'nplc': 1, 'samples': 3},
        MeasurementQuality.MEDIUM: {'nplc': 5, 'samples': 5},
        MeasurementQuality.LONG: {'nplc': 10, 'samples': 10},
        MeasurementQuality.CUSTOM: {'nplc': None, 'samples': None}
    }
    
class WireMode(Enum):
    """Wire configuration mode for measurements"""
    WIRE_2 = '2WIRE'
    WIRE_4 = '4WIRE'

class B2902B:
    """
    Enhanced Keysight B2902B SMU Control Class
    
    Features:
    - Basic voltage/current sourcing and measurement
    - Continuous monitoring with data logging
    - Automated Id-Vds measurements
    - Transfer curve measurements
    - Data visualization support
    """
    
    def __init__(self, resource_name: str = None, timeout: int = 10000):
        """
        Initialize SMU controller
        
        Args:
            resource_name: VISA resource name
            timeout: Communication timeout in milliseconds
        """
        self.resource_name = resource_name
        self.timeout = timeout
        self.smu = None
        self.rm = None
        self._setup_logging()
        self.monitoring_data = {
            Channel.CH1: {'time': [], 'voltage': [], 'current': []},
            Channel.CH2: {'time': [], 'voltage': [], 'current': []}
        }
        
    def _setup_logging(self):
        """Configure logging system"""
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

    def connect(self, resource_name: str = None) -> bool:
        """
        Connect to SMU and perform initial setup
        
        Args:
            resource_name: Optional new resource name
            
        Returns:
            bool: Connection success status
        """
        try:
            self.rm = pyvisa.ResourceManager()
            self.resource_name = resource_name or self.resource_name
            
            if not self.resource_name:
                raise ConnectionError("No resource name provided")
                
            self.smu = self.rm.open_resource(self.resource_name)
            self._configure_connection()
            self._initialize_instrument()
            
            idn = self.smu.query("*IDN?")
            self.logger.info(f"Connected to: {idn.strip()}")
            return True
            
        except Exception as e:
            self.logger.error(f"Connection failed: {str(e)}")
            return False
            
    def _configure_connection(self):
        """Configure connection parameters"""
        self.smu.timeout = self.timeout
        self.smu.read_termination = '\n'
        self.smu.write_termination = '\n'
        self.smu.chunk_size = 102400
        
    def _initialize_instrument(self):
        """Initialize instrument settings"""
        self.smu.write("*RST")
        self.smu.write("*CLS")
        self.smu.write(":FORM:DATA ASC")
        self.smu.write(":SENS:CURR:NPLC 0.1")
        self.smu.write(":SENS:VOLT:NPLC 0.1")
        
    def configure_wire_mode(self, channel: Channel, mode: WireMode) -> bool:
        """
        Configure the wire mode (2-wire or 4-wire) for a specific channel
        
        Args:
            channel: Target channel
            mode: Wire configuration mode (2-wire or 4-wire)
            
        Returns:
            bool: Configuration success status
        """
        try:
            ch = channel.value
            if mode == WireMode.WIRE_4:
                self.smu.write(f":SENS{ch}:REM ON")  # Enable 4-wire remote sensing
                self.logger.info(f"Channel {ch} set to 4-wire mode")
            else:
                self.smu.write(f":SENS{ch}:REM OFF")  # Disable 4-wire remote sensing
                self.logger.info(f"Channel {ch} set to 2-wire mode")
            
            # Verify configuration
            sense_mode = self.smu.query(f":SENS{ch}:REM?")
            expected_mode = "1" if mode == WireMode.WIRE_4 else "0"
            
            if sense_mode.strip() == expected_mode:
                return True
            else:
                self.logger.error(f"Wire mode configuration verification failed for channel {ch}")
                return False
                
        except Exception as e:
            self.logger.error(f"Wire mode configuration error: {str(e)}")
            return False
        
    def configure_output(self, 
                        channel: Channel,
                        mode: OutputMode,
                        level: float,
                        compliance: float,
                        auto_range: bool = True) -> bool:
        """
        Configure output settings for specified channel
        
        Args:
            channel: Target channel (CH1 or CH2)
            mode: Output mode (VOLTAGE or CURRENT)
            level: Output level (V or A)
            compliance: Compliance level
            auto_range: Enable auto-ranging
            
        Returns:
            bool: Configuration success status
        """
        try:
            ch = channel.value
            mode_str = mode.value
            
            # Configure source mode and level
            self.smu.write(f":SOUR{ch}:FUNC:MODE {mode_str}")
            self.smu.write(f":SOUR{ch}:{mode_str} {level}")
            
            # Set compliance based on mode
            comp_mode = "CURR" if mode == OutputMode.VOLTAGE else "VOLT"
            self.smu.write(f":SENS{ch}:{comp_mode}:PROT {compliance}")
            
            # Configure ranging
            if auto_range:
                self.smu.write(f":SOUR{ch}:{mode_str}:RANG:AUTO ON")
                self.smu.write(f":SENS{ch}:{comp_mode}:RANG:AUTO ON")
            
            self.logger.info(
                f"Channel {ch} configured: {mode_str}={level}, "
                f"Compliance={compliance}"
            )
            return True
            
        except Exception as e:
            self.logger.error(f"Output configuration error: {str(e)}")
            return False

    def read_values(self, channel: Channel) -> Dict[str, float]:
        """
        Read current measurement values from specified channel
        
        Args:
            channel: Target channel
            
        Returns:
            Dict containing voltage and current readings
        """
        try:
            ch = channel.value
            voltage = float(self.smu.query(f":MEAS:VOLT? (@{ch})"))
            current = float(self.smu.query(f":MEAS:CURR? (@{ch})"))
            
            return {
                'voltage': voltage,
                'current': current,
                'timestamp': time.time()
            }
        except Exception as e:
            self.logger.error(f"Measurement error: {str(e)}")
            return None

    def start_monitoring(self, 
                        channel: Channel,
                        interval: float) -> bool:
        """
        Start continuous monitoring of specified channel
        
        Args:
            channel: Target channel
            interval: Measurement interval in seconds
            
        Returns:
            bool: Monitoring start success status
        """
        try:
            # Clear previous monitoring data
            self.monitoring_data[channel] = {
                'time': [],
                'voltage': [],
                'current': []
            }
            
            start_time = time.time()
            while True:
                values = self.read_values(channel)
                if values:
                    self.monitoring_data[channel]['time'].append(
                        values['timestamp'] - start_time
                    )
                    self.monitoring_data[channel]['voltage'].append(
                        values['voltage']
                    )
                    self.monitoring_data[channel]['current'].append(
                        values['current']
                    )
                
                time.sleep(interval)
                
            return True
            
        except Exception as e:
            self.logger.error(f"Monitoring error: {str(e)}")
            return False

    def export_monitoring_data(self,
                            channel: Channel,
                            filename: str) -> bool:
        """
        Export monitoring data to CSV file
        
        Args:
            channel: Target channel
            filename: Output filename
            
        Returns:
            bool: Export success status
        """
        try:
            data = self.monitoring_data[channel]
            df = pd.DataFrame({
                'Time(s)': data['time'],
                'Voltage(V)': data['voltage'],
                'Current(A)': data['current']
            })
            
            df.to_csv(filename, index=False)
            self.logger.info(f"Data exported to {filename}")
            return True
            
        except Exception as e:
            self.logger.error(f"Data export error: {str(e)}")
            return False
        
    def enable_output(self, channel: Channel) -> bool:
        """
        Enable output for specified channel
        
        Args:
            channel: Target channel (CH1 or CH2)
            
        Returns:
            bool: Operation success status
        """
        try:
            ch = channel.value
            self.smu.write(f":OUTP{ch} ON")
            time.sleep(0.1)  # Wait for output to stabilize
            
            # Verify output status
            if int(self.smu.query(f":OUTP{ch}?")):
                self.logger.info(f"Channel {ch} output enabled")
                return True
            else:
                self.logger.error(f"Failed to enable channel {ch} output")
                return False
                
        except Exception as e:
            self.logger.error(f"Enable output error: {str(e)}")
            return False

    def disable_output(self, channel: Channel) -> bool:
        """
        Disable output for specified channel
        
        Args:
            channel: Target channel (CH1 or CH2)
            
        Returns:
            bool: Operation success status
        """
        try:
            ch = channel.value
            self.smu.write(f":OUTP{ch} OFF")
            time.sleep(0.1)  # Wait for output to stabilize
            
            # Verify output status
            if not int(self.smu.query(f":OUTP{ch}?")):
                self.logger.info(f"Channel {ch} output disabled")
                return True
            else:
                self.logger.error(f"Failed to disable channel {ch} output")
                return False
                
        except Exception as e:
            self.logger.error(f"Disable output error: {str(e)}")
            return False

    def get_output_state(self, channel: Channel) -> bool:
        """
        Get current output state for specified channel
        
        Args:
            channel: Target channel (CH1 or CH2)
            
        Returns:
            bool: True if output is enabled, False if disabled
        """
        try:
            ch = channel.value
            state = bool(int(self.smu.query(f":OUTP{ch}?")))
            return state
            
        except Exception as e:
            self.logger.error(f"Get output state error: {str(e)}")
            return False
        
    def _measure_with_quality(self, 
                            channel: Channel, 
                            quality: MeasurementQuality,
                            custom_nplc: float = None,
                            custom_samples: int = None) -> Dict[str, float]:
        """
        Perform measurement with specified quality settings
        
        Args:
            channel: Target channel
            quality: Measurement quality level
            custom_nplc: Custom NPLC value for CUSTOM quality mode
            custom_samples: Custom number of samples for CUSTOM quality mode
            
        Returns:
            Dict containing averaged voltage and current readings
            
        Raises:
            ValueError: If CUSTOM quality is selected but custom parameters are not provided
        """
        settings = QualitySettings.SETTINGS[quality].copy()
        
        if quality == MeasurementQuality.CUSTOM:
            if custom_nplc is None or custom_samples is None:
                raise ValueError(
                    "Custom NPLC and samples must be provided when using CUSTOM quality mode"
                )
            settings['nplc'] = custom_nplc
            settings['samples'] = custom_samples
            
            # Validate custom settings
            if not (0.01 <= custom_nplc <= 100):
                raise ValueError("NPLC must be between 0.01 and 100")
            if not (1 <= custom_samples <= 100):
                raise ValueError("Number of samples must be between 1 and 100")
        
        ch = channel.value
        
        # Set NPLC
        self.smu.write(f":SENS{ch}:CURR:NPLC {settings['nplc']}")
        self.smu.write(f":SENS{ch}:VOLT:NPLC {settings['nplc']}")
        
        # Collect multiple samples
        voltages = []
        currents = []
        for _ in range(settings['samples']):
            voltage = float(self.smu.query(f":MEAS:VOLT? (@{ch})"))
            current = float(self.smu.query(f":MEAS:CURR? (@{ch})"))
            voltages.append(voltage)
            currents.append(current)
            time.sleep(0.01)
        
        # Calculate averages and statistics
        return {
            'voltage': np.mean(voltages),
            'current': np.mean(currents),
            'voltage_std': np.std(voltages),
            'current_std': np.std(currents),
            'nplc': settings['nplc'],
            'samples': settings['samples'],
            'timestamp': time.time()
        }
        
    ##########  Id-Vds Measurement  ##########
    def measure_id_vds(self,
                    vgs_start: float,
                    vgs_stop: float,
                    vgs_step: float,
                    vds_start: float,
                    vds_stop: float,
                    vds_step: float,
                    measurement_quality: MeasurementQuality,
                    drain_wire_mode: WireMode = WireMode.WIRE_2,
                    gate_wire_mode: WireMode = WireMode.WIRE_2,
                    custom_nplc: float = None,
                    custom_samples: int = None,
                    sweep_back: bool = False,
                    delay: float = 0.1) -> Dict:
        """
        Perform Id-Vds characteristic measurement with customizable quality control and wire mode
        
        The measurement defaults to 2-wire mode for both channels, which is suitable for most
        applications. 4-wire mode can be specified when higher measurement accuracy is required,
        particularly for low-resistance measurements or when using long test leads.
        
        Args:
            vgs_start: Start voltage for Vgs
            vgs_stop: Stop voltage for Vgs
            vgs_step: Voltage step for Vgs
            vds_start: Start voltage for Vds sweep
            vds_stop: Stop voltage for Vds sweep
            vds_step: Voltage step for Vds sweep
            measurement_quality: Quality setting for measurements
            drain_wire_mode: Wire configuration for drain measurement (defaults to 2-wire)
            gate_wire_mode: Wire configuration for gate measurement (defaults to 2-wire)
            custom_nplc: Custom NPLC value if using CUSTOM quality
            custom_samples: Custom sample count if using CUSTOM quality
            sweep_back: Whether to perform reverse sweep
            delay: Delay between measurements (seconds)
            
        Returns:
            Dictionary containing measurement results and metadata
        """
        try:
            measurement_data = {
                'point_id': [],
                'vgs': [],
                'vds': [],
                'ids': [],
                'ids_std': [],
                'igs': [],
                'igs_std': [],
                'sweep_type': [],
                'configuration': {
                    'quality_settings': {
                        'mode': measurement_quality.value,
                        'nplc': custom_nplc if measurement_quality == MeasurementQuality.CUSTOM 
                                else QualitySettings.SETTINGS[measurement_quality]['nplc'],
                        'samples': custom_samples if measurement_quality == MeasurementQuality.CUSTOM 
                                else QualitySettings.SETTINGS[measurement_quality]['samples']
                    },
                    'wire_settings': {
                        'drain': drain_wire_mode.value,
                        'gate': gate_wire_mode.value
                    }
                }
            }
            
            # Configure wire modes
            if not self.configure_wire_mode(Channel.CH1, drain_wire_mode):
                raise Exception("Failed to configure drain wire mode")
            if not self.configure_wire_mode(Channel.CH2, gate_wire_mode):
                raise Exception("Failed to configure gate wire mode")
            
            # Calculate Vgs and Vds points
            vgs_points = np.arange(vgs_start, vgs_stop + vgs_step, vgs_step)
            vds_points = np.arange(vds_start, vds_stop + vds_step, vds_step)
            if sweep_back:
                vds_backward = np.arange(vds_stop, vds_start - vds_step, -vds_step)
            
            # Configure channels initial setup
            self._setup_channels_for_id_vds()
            
            # Perform measurement for each Vgs
            for curve_idx, vgs in enumerate(vgs_points, 1):
                # Set gate voltage
                self.smu.write(f":SOUR2:VOLT {vgs}")
                time.sleep(delay)
                
                # Forward sweep
                for point_idx, vds in enumerate(vds_points, 1):
                    self._measure_id_vds_point(
                        measurement_data,
                        vgs, vds,
                        f"{curve_idx}.1.{point_idx}",
                        'forward',
                        measurement_quality,
                        custom_nplc,
                        custom_samples,
                        delay
                    )
                
                # Backward sweep if enabled
                if sweep_back:
                    for point_idx, vds in enumerate(vds_backward, 1):
                        self._measure_id_vds_point(
                            measurement_data,
                            vgs, vds,
                            f"{curve_idx}.2.{point_idx}",
                            'backward',
                            measurement_quality,
                            custom_nplc,
                            custom_samples,
                            delay
                        )
            
            return measurement_data
            
        except Exception as e:
            self.logger.error(f"Id-Vds measurement error: {str(e)}")
            self._safe_shutdown()
            return None

    def _measure_id_vds_point(self,
                            data: Dict,
                            vgs: float,
                            vds: float,
                            point_id: str,
                            sweep_type: str,
                            quality: MeasurementQuality,
                            custom_nplc: float,
                            custom_samples: int,
                            delay: float):
        """
        Measure single point in Id-Vds characteristic with quality control
        """
        # Set drain voltage
        self.smu.write(f":SOUR1:VOLT {vds}")
        time.sleep(delay)
        
        # Measure with specified quality settings
        drain_values = self._measure_with_quality(
            Channel.CH1, 
            quality,
            custom_nplc,
            custom_samples
        )
        
        gate_values = self._measure_with_quality(
            Channel.CH2,
            quality,
            custom_nplc,
            custom_samples
        )
        
        # Store data with statistical information
        data['point_id'].append(point_id)
        data['vgs'].append(vgs)
        data['vds'].append(drain_values['voltage'])
        data['ids'].append(drain_values['current'])
        data['ids_std'].append(drain_values['current_std'])
        data['igs'].append(gate_values['current'])
        data['igs_std'].append(gate_values['current_std'])
        data['sweep_type'].append(sweep_type)
        
        
    ##########  Transfer Curve Measurement  ##########
    def measure_transfer_curve(self,
                            vds_values: List[float],
                            vgs_start: float,
                            vgs_stop: float,
                            vgs_step: float,
                            measurement_quality: MeasurementQuality,
                            drain_wire_mode: WireMode = WireMode.WIRE_2,
                            gate_wire_mode: WireMode = WireMode.WIRE_2,
                            custom_nplc: float = None,
                            custom_samples: int = None,
                            sweep_back: bool = False,
                            delay: float = 0.1) -> Dict:
        """
        Perform transfer curve (Id-Vgs) measurements at different Vds values
        
        This function measures the drain current as a function of gate voltage
        at specified drain-source voltages. For each Vds value, it performs
        a complete Vgs sweep to characterize the device's transfer characteristics.
        
        Args:
            vds_values: List of drain-source voltages to measure at
            vgs_start: Start voltage for Vgs sweep
            vgs_stop: Stop voltage for Vgs sweep
            vgs_step: Voltage step for Vgs sweep
            measurement_quality: Quality setting for measurements
            drain_wire_mode: Wire configuration for drain measurement (defaults to 2-wire)
            gate_wire_mode: Wire configuration for gate measurement (defaults to 2-wire)
            custom_nplc: Custom NPLC value if using CUSTOM quality
            custom_samples: Custom sample count if using CUSTOM quality
            sweep_back: Whether to perform reverse sweep
            delay: Delay between measurements (seconds)
            
        Returns:
            Dictionary containing measurement results and metadata
        """
        try:
            # Initialize data storage
            measurement_data = {
                'point_id': [],      # Format: curve_number.sweep_direction.point_number
                'vds': [],          # Drain-source voltage
                'vgs': [],          # Gate voltage
                'ids': [],          # Drain current
                'ids_std': [],      # Standard deviation of drain current
                'igs': [],          # Gate current
                'igs_std': [],      # Standard deviation of gate current
                'sweep_type': [],   # 'forward' or 'backward'
                'configuration': {
                    'quality_settings': {
                        'mode': measurement_quality.value,
                        'nplc': custom_nplc if measurement_quality == MeasurementQuality.CUSTOM 
                                else QualitySettings.SETTINGS[measurement_quality]['nplc'],
                        'samples': custom_samples if measurement_quality == MeasurementQuality.CUSTOM 
                                else QualitySettings.SETTINGS[measurement_quality]['samples']
                    },
                    'wire_settings': {
                        'drain': drain_wire_mode.value,
                        'gate': gate_wire_mode.value
                    }
                }
            }
            
            # Configure wire modes
            self.configure_wire_mode(Channel.CH1, drain_wire_mode)
            self.configure_wire_mode(Channel.CH2, gate_wire_mode)
            
            # Calculate Vgs points
            vgs_points = np.arange(vgs_start, vgs_stop + vgs_step, vgs_step)
            if sweep_back:
                vgs_backward = np.arange(vgs_stop, vgs_start - vgs_step, -vgs_step)
            
            # Configure channels initial setup
            self._setup_channels_for_transfer_curve()
            
            # Perform measurement for each Vds
            for curve_idx, vds in enumerate(vds_values, 1):
                # Set drain voltage
                self.smu.write(f":SOUR1:VOLT {vds}")
                time.sleep(delay)
                
                # Forward sweep
                for point_idx, vgs in enumerate(vgs_points, 1):
                    self._measure_transfer_point(
                        measurement_data,
                        vds, vgs,
                        f"{curve_idx}.1.{point_idx}",
                        'forward',
                        measurement_quality,
                        custom_nplc,
                        custom_samples,
                        delay
                    )
                
                # Backward sweep if enabled
                if sweep_back:
                    for point_idx, vgs in enumerate(vgs_backward, 1):
                        self._measure_transfer_point(
                            measurement_data,
                            vds, vgs,
                            f"{curve_idx}.2.{point_idx}",
                            'backward',
                            measurement_quality,
                            custom_nplc,
                            custom_samples,
                            delay
                        )
            
            return measurement_data
            
        except Exception as e:
            self.logger.error(f"Transfer curve measurement error: {str(e)}")
            self._safe_shutdown()
            return None

    def _setup_channels_for_transfer_curve(self):
        """Configure initial channel settings for transfer curve measurement"""
        # Channel 1 (Drain-Source)
        self.configure_output(
            channel=Channel.CH1,
            mode=OutputMode.VOLTAGE,
            level=0,
            compliance=0.1  # 100mA compliance
        )
        
        # Channel 2 (Gate)
        self.configure_output(
            channel=Channel.CH2,
            mode=OutputMode.VOLTAGE,
            level=0,
            compliance=0.01  # 10mA compliance
        )
        
        # Enable outputs
        self.enable_output(Channel.CH1)
        self.enable_output(Channel.CH2)

    def _measure_transfer_point(self,
                            data: Dict,
                            vds: float,
                            vgs: float,
                            point_id: str,
                            sweep_type: str,
                            quality: MeasurementQuality,
                            custom_nplc: float,
                            custom_samples: int,
                            delay: float):
        """
        Measure single point in transfer curve measurement
        """
        # Set gate voltage
        self.smu.write(f":SOUR2:VOLT {vgs}")
        time.sleep(delay)
        
        # Measure with specified quality settings
        drain_values = self._measure_with_quality(
            Channel.CH1, 
            quality,
            custom_nplc,
            custom_samples
        )
        
        gate_values = self._measure_with_quality(
            Channel.CH2,
            quality,
            custom_nplc,
            custom_samples
        )
        
        # Store data with statistical information
        data['point_id'].append(point_id)
        data['vds'].append(vds)
        data['vgs'].append(vgs)
        data['ids'].append(drain_values['current'])
        data['ids_std'].append(drain_values['current_std'])
        data['igs'].append(gate_values['current'])
        data['igs_std'].append(gate_values['current_std'])
        data['sweep_type'].append(sweep_type)
    
    