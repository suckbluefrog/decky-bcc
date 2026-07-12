export interface PowerProfile {
  label: string;
  cpu_governor: string;
  cpu_max: string;
  cpu_underclock: string;
  gpu_max: string;
  gpu_min: string;
  fan_curve: string;
}

export interface FanCurve {
  label: string;
  curve: string;
}

export interface PowerConfig {
  general: { default_profile: string };
  profiles: Record<string, PowerProfile>;
  fan_curves: Record<string, FanCurve>;
  fan: Record<string, string>;
  underclocks: Record<string, Record<string, Record<string, string>>>;
}

export interface GameTweak {
  enabled?: boolean;
  name?: string;
  fexProfile?: string;
  fexConfig?: Record<string, string>;
  thunks?: Record<string, boolean>;
  [key: string]: any;
}

export interface Tweaks {
  global: Record<string, any>;
  games: Record<string, GameTweak>;
}

export interface InstalledGame {
  appid: string;
  name: string;
}

export interface FexProfile {
  label: string;
  config?: Record<string, string>;
}

export interface AbsControl {
  value: number;
  min: number;
  max: number;
  flat: number;
  fuzz: number;
  resolution: number;
}

export interface CalibrationState {
  supported: boolean;
  reason: string;
  controls: Record<string, AbsControl>;
  event: any;
  canApply?: boolean;
  backend?: string;
  saved?: boolean;
  params?: Record<string, number>;
}

export interface GameRef {
  appid: string;
  name: string;
}

export interface JoystickLedSide {
  mode: string;
  color: string;
  brightness: number;
}

export interface JoystickLedConfig {
  left: JoystickLedSide;
  right: JoystickLedSide;
  linked: boolean;
}

export interface JoystickLedState {
  supported: boolean;
  reason?: string;
  modes: DropdownChoice[];
  colors: DropdownChoice[];
  config: JoystickLedConfig;
}

export interface OledCareConfig {
  ENABLED: number;
  BRIGHTNESS_NORMAL: number;
  BRIGHTNESS_IDLE: number;
  IDLE_DIM_SECONDS: number;
}

export interface OledCareRuntime {
  serviceRunning: boolean;
  monitorRunning: boolean;
  idleSeconds: number;
  brightnessPct: number | null;
}

export interface OledCareState {
  supported: boolean;
  reason?: string;
  config: OledCareConfig;
  labels: Record<string, string>;
  runtime: OledCareRuntime;
}

export interface BackPaddleBindings {
  m1: string;
  m2: string;
  m1_m2: string;
  m1_start: string;
  m1_back: string;
  select_m2: string;
  home_m2: string;
}

export interface BackPaddleState {
  supported: boolean;
  reason?: string;
  warning?: string;
  bindings: BackPaddleBindings;
  slots: DropdownChoice[];
  actions: DropdownChoice[];
}

export interface LsfgConfig {
  enabled: boolean;
  multiplier: string;
  flowScale: string;
  performanceMode: boolean;
  hdrMode: boolean;
  presentMode: string;
}

export interface LsfgState {
  supported: boolean;
  reason: string;
  ready: boolean;
  dllDetected: boolean;
  dllPath: string;
  layers: { native: boolean; x64: boolean };
  config: LsfgConfig;
  legacyPluginDetected: boolean;
  legacyConfigDetected: boolean;
  legacyLaunchScriptDetected: boolean;
  appliesOnNextSteamLaunch: boolean;
}

export interface Config {
  power: PowerConfig;
  powerDefaults: PowerConfig;
  powerSupported: boolean;
  powerReason: string;
  tweaks: Tweaks;
  installedGames: InstalledGame[];
  fexProfiles: Record<string, FexProfile>;
  fexRuntimeSupported: boolean;
  fexRuntimeReason: string;
  launchWrapperPath: string;
  cpuDeviceClass: string;
  osVersion: string;
  sshEnabled: boolean;
  controllerSupported: boolean;
  controllerType: string;
  controllerTypes: DropdownChoice[];
  joystickLed?: JoystickLedState;
  joystickLedColors?: DropdownChoice[];
  joystickLedModes?: DropdownChoice[];
  joystickLedPresets?: Record<string, string>;
  oledCare?: OledCareState;
  backPaddles?: BackPaddleState;
  lsfg?: LsfgState;
  calibration?: CalibrationState;
  game?: GameRef | null;
  selectedGame?: GameRef | null;
  warnings?: string[];
}

export type Capture = Record<string, { center: number; min: number; max: number; range: number }>;

export interface DropdownChoice {
  data: string;
  label: string;
}
