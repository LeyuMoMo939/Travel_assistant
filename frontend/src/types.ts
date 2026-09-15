/** 与后端 app/models/schemas.py 一一对应的 TypeScript 类型 —— 前后端共享一套数据契约 */

export interface TripRequest {
  city: string
  start_date: string
  travel_days: number
  transportation: string
  accommodation: string
  preferences: string[]
  other_requirements?: string
}

export interface Location {
  longitude: number
  latitude: number
}

export interface WeatherInfo {
  date: string
  day_weather: string
  night_weather: string
  day_temp: number | string
  night_temp: number | string
  wind_direction: string
  wind_power: string
}

export interface Attraction {
  name: string
  address: string
  location?: Location
  visit_duration: number
  description: string
  ticket_price: number
}

export interface Meal {
  type: string // breakfast / lunch / dinner
  name: string
  description: string
  estimated_cost: number
}

export interface Hotel {
  name: string
  address: string
  estimated_cost: number
}

export interface DayPlan {
  date: string
  day_index: number
  description: string
  attractions: Attraction[]
  meals: Meal[]
  hotel?: Hotel | null
}

export interface Budget {
  total_attractions: number
  total_hotels: number
  total_meals: number
  total: number
  /** 住宿晚数:N 天行程 N-1 晚(当天往返为 0) */
  nights: number
}

export interface TripPlan {
  city: string
  start_date: string
  end_date: string
  days: DayPlan[]
  weather_info: WeatherInfo[]
  overall_suggestions: string
  budget?: Budget | null
}

export interface TripPlanResponse {
  success: boolean
  message: string
  data?: TripPlan
}
