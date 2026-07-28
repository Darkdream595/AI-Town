/**
 * 居民 API 类型定义
 *
 * 对应后端 ResidentSummary 和 ResidentDetail 模型
 */

/**
 * 居民摘要（列表展示）
 */
export interface ResidentSummary {
  resident_id: string;
  name: string;
  race: string;
  profession: string | null;
  current_scene_id: string;
  health_status: string;
  current_hp: number;
  max_hp: number;
}

/**
 * 居民详情（完整信息）
 */
export interface ResidentDetail {
  resident_id: string;
  name: string;
  race: string;
  gender: string;
  age_years: number;
  profession: string | null;
  current_scene_id: string;

  // 外观
  sprite_id: string;
  skin_tone: string;
  hair_color: string;

  // 健康
  health_status: string;
  current_hp: number;
  max_hp: number;

  // 需求
  hunger: number;
  energy: number;
  social: number;

  // 情绪
  joy: number;
  fear: number;
  anger: number;
}

/**
 * 居民 API 客户端
 */
export class ResidentsAPI {
  private baseUrl: string;

  constructor(baseUrl: string = 'http://127.0.0.1:18000') {
    this.baseUrl = baseUrl;
  }

  /**
   * 获取所有居民列表
   */
  async getResidents(): Promise<ResidentSummary[]> {
    const response = await fetch(`${this.baseUrl}/api/residents/`);
    if (!response.ok) {
      throw new Error(`Failed to fetch residents: ${response.statusText}`);
    }
    return response.json();
  }

  /**
   * 获取单个居民详情
   */
  async getResident(residentId: string): Promise<ResidentDetail> {
    const response = await fetch(`${this.baseUrl}/api/residents/${residentId}`);
    if (!response.ok) {
      throw new Error(`Failed to fetch resident ${residentId}: ${response.statusText}`);
    }
    return response.json();
  }

  /**
   * 获取居民总数
   */
  async getResidentCount(): Promise<number> {
    const response = await fetch(`${this.baseUrl}/api/residents/count`);
    if (!response.ok) {
      throw new Error(`Failed to fetch resident count: ${response.statusText}`);
    }
    const data = await response.json();
    return data.count;
  }
}

/**
 * 默认 API 实例
 */
export const residentsAPI = new ResidentsAPI();
