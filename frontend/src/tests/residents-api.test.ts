/**
 * 居民 API 测试
 *
 * 测试与后端的连接和数据获取
 */

import { residentsAPI, ResidentSummary, ResidentDetail } from '../api/residents';

async function testResidentsAPI() {
  console.log('=== 测试居民 API ===\n');

  try {
    // 测试 1: 获取居民总数
    console.log('1. 获取居民总数...');
    const count = await residentsAPI.getResidentCount();
    console.log(`   ✅ 居民总数: ${count}\n`);

    // 测试 2: 获取居民列表
    console.log('2. 获取居民列表...');
    const residents = await residentsAPI.getResidents();
    console.log(`   ✅ 获取到 ${residents.length} 个居民:`);
    residents.forEach((r: ResidentSummary) => {
      console.log(`      - ${r.name} (${r.race}, ${r.profession || '无职业'})`);
    });
    console.log('');

    // 测试 3: 获取单个居民详情
    if (residents.length > 0) {
      const firstResident = residents[0];
      console.log(`3. 获取居民详情: ${firstResident.name}...`);
      const detail = await residentsAPI.getResident(firstResident.resident_id);
      console.log(`   ✅ 详情获取成功:`);
      console.log(`      姓名: ${detail.name}`);
      console.log(`      年龄: ${detail.age_years} 岁`);
      console.log(`      健康: ${detail.health_status} (${detail.current_hp}/${detail.max_hp})`);
      console.log(`      需求: 饥饿=${detail.hunger}, 精力=${detail.energy}, 社交=${detail.social}`);
      console.log(`      情绪: 喜悦=${detail.joy}, 恐惧=${detail.fear}, 愤怒=${detail.anger}`);
    }

    console.log('\n=== 所有测试通过 ✅ ===');
  } catch (error) {
    console.error('❌ 测试失败:', error);
  }
}

// 如果直接运行此文件，执行测试
if (typeof window !== 'undefined') {
  // 浏览器环境
  window.addEventListener('load', () => {
    testResidentsAPI();
  });
} else {
  // Node.js 环境
  testResidentsAPI();
}

export { testResidentsAPI };
