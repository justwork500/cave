import {
  BatteryChargeRegular, BedRegular, CameraRegular, ClockRegular, DoorRegular, DropRegular, FireRegular, HomeRegular,
  LightbulbRegular, LockClosedRegular, PlayRegular, PlugConnectedRegular, PowerRegular, ShieldRegular,
  Speaker2Regular, TemperatureRegular, TvRegular, WeatherSnowflakeRegular, WeatherSquallsRegular, WeatherSunnyRegular,
} from "@fluentui/react-icons";

/** The icons and colours a card can have: the same sets as CardIcon and CardColor in the core. */
export const ICONS = {
  lightbulb: LightbulbRegular, plug: PlugConnectedRegular, power: PowerRegular, wind: WeatherSquallsRegular,
  fire: FireRegular, temperature: TemperatureRegular, drop: DropRegular, sun: WeatherSunnyRegular,
  snow: WeatherSnowflakeRegular, door: DoorRegular, lock: LockClosedRegular, shield: ShieldRegular,
  camera: CameraRegular, speaker: Speaker2Regular, tv: TvRegular, home: HomeRegular, bed: BedRegular,
  clock: ClockRegular, play: PlayRegular, battery: BatteryChargeRegular,
};

export const COLORS = ["blue", "green", "amber", "red", "purple"] as const;

export function CardIcon({ name }: { name?: string | null }) {
  const Icon = name ? ICONS[name as keyof typeof ICONS] : undefined;
  return Icon ? <Icon className="card-icon" aria-hidden /> : null;
}
