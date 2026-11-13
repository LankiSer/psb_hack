import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  devIndicators: false,
  async headers(){return [{source:"/office-agent/:path*",headers:[{key:"Access-Control-Allow-Origin",value:"*"}]}]},
};

export default nextConfig;
