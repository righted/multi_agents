from fastmcp import FastMCP

mcp = FastMCP("math")

@mcp.tool()
def add(a:float, b:float):
    """两数相加"""
    return a+b

@mcp.tool()
def subtract(a: float,b: float):
    """两数相减"""
    return a-b

if __name__ =="__main__":
    mcp.run(transport="stdio")
