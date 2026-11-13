/** Sunlit chart styling shared by overview and platform details. */
export function chartTheme(option:any){
 const ink='#587b90',line='#c5dbe5';
 const axes=(value:any)=>{
  const style=(axis:any)=>({...axis,nameTextStyle:{...axis.nameTextStyle,color:ink},splitLine:{...axis.splitLine,show:false},axisLabel:{...axis.axisLabel,color:ink},axisLine:{...axis.axisLine,lineStyle:{...axis.axisLine?.lineStyle,color:line}}});
  return Array.isArray(value)?value.map(style):value?style(value):value;
 };
 const colors:Record<string,string>={'#a498e5':'#389aa9','#82a7ed':'#328fbb','#efbd69':'#368fac','#ed947d':'#be8a65','#6bbad2':'#369cae','#2897d6':'#328fbb','#ffc458':'#b18a46','#c9b78e':'#389aa9'};
 const legend=(value:any)=>({...value,textStyle:{...value.textStyle,color:ink},inactiveColor:'#b6cbd5'});
 return {...option,textStyle:{...option.textStyle,color:ink},
  ...(option.legend?{legend:Array.isArray(option.legend)?option.legend.map(legend):legend(option.legend)}:{}),
  ...(option.tooltip?{tooltip:{valueFormatter:(value:unknown)=>typeof value==='number'&&Number.isFinite(value)?value.toFixed(2):value==null?'—':String(value),...option.tooltip,backgroundColor:'#f8fcff',borderColor:'#c8dfe9',textStyle:{...option.tooltip.textStyle,color:'#416d84'},extraCssText:'box-shadow:0 5px 20px #385d4920;border-radius:10px;'}}:{}),
  ...(option.yAxis?{yAxis:axes(option.yAxis)}:{}),
  ...(option.xAxis?{xAxis:axes(option.xAxis)}:{}),
  ...(option.series?{series:option.series.map((series:any)=>{
   const original=series.lineStyle?.color||series.itemStyle?.color;
   const color=series.name==='昨日'?'#859ab5':series.yAxisIndex===1?'#b18a46':colors[original]||'#328faf';
   return {...series,itemStyle:{...series.itemStyle,color,...(series.itemStyle?.borderColor?{borderColor:color}:{})},lineStyle:{...series.lineStyle,color},...(series.areaStyle?{areaStyle:{...series.areaStyle,color,opacity:.08}}:{})};
  })}:{}),
 };
}
