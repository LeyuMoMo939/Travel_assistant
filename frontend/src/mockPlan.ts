import type { TripPlanResponse } from './types'

/**
 * 后端未启动时用的示例数据,仅供开发模式预览页面样式。
 *
 * 单独放一个文件是为了让它能用 `import('./mockPlan')` 动态引入 ——
 * 生产构建里这段代码不会被加载,演示数据也就不进主包了。
 */
export const MOCK_PLAN: TripPlanResponse = {
  success: true,
  message: 'mock',
  data: {
    city: '北京',
    start_date: '2026-10-01',
    end_date: '2026-10-02',
    days: [
      {
        date: '2026-10-01',
        day_index: 0,
        description: '经典中轴线一日游',
        attractions: [
          {
            name: '故宫博物院',
            address: '景山前街4号',
            location: { longitude: 116.397, latitude: 39.918 },
            visit_duration: 180,
            description: '明清两代皇宫,世界文化遗产',
            ticket_price: 60,
          },
          {
            name: '景山公园',
            address: '景山西街44号',
            location: { longitude: 116.397, latitude: 39.925 },
            visit_duration: 90,
            description: '登万春亭俯瞰故宫全景',
            ticket_price: 2,
          },
        ],
        meals: [
          { type: 'breakfast', name: '护国寺小吃', description: '豆汁儿焦圈', estimated_cost: 20 },
          { type: 'lunch', name: '四季民福烤鸭', description: '故宫店观景位', estimated_cost: 150 },
          { type: 'dinner', name: '南门涮肉', description: '铜锅涮肉', estimated_cost: 100 },
        ],
        hotel: { name: '如家精选(王府井店)', address: '王府井大街', estimated_cost: 350 },
      },
      {
        date: '2026-10-02',
        day_index: 1,
        description: '皇家园林与胡同',
        attractions: [
          {
            name: '颐和园',
            address: '新建宫门路19号',
            location: { longitude: 116.275, latitude: 39.999 },
            visit_duration: 240,
            description: '中国现存最大的皇家园林',
            ticket_price: 30,
          },
        ],
        meals: [
          { type: 'breakfast', name: '庆丰包子铺', description: '猪肉大葱包子', estimated_cost: 15 },
          { type: 'lunch', name: '听鹂馆', description: '颐和园内宫廷菜', estimated_cost: 120 },
          { type: 'dinner', name: '局气', description: '京味创意菜', estimated_cost: 90 },
        ],
        hotel: { name: '如家精选(王府井店)', address: '王府井大街', estimated_cost: 350 },
      },
    ],
    weather_info: [
      { date: '2026-10-01', day_weather: '晴', night_weather: '多云', day_temp: 24, night_temp: 13, wind_direction: '南风', wind_power: '1-3级' },
      { date: '2026-10-02', day_weather: '多云', night_weather: '晴', day_temp: 22, night_temp: 12, wind_direction: '北风', wind_power: '1-3级' },
    ],
    overall_suggestions: '十月初北京秋高气爽,适合出行;故宫需提前7天在官方小程序预约购票。',
    // 2 天行程 = 1 晚;住宿 350 × 1 = 350
    budget: { total_attractions: 92, total_hotels: 350, total_meals: 495, total: 937, nights: 1 },
  },
}
