<*
 @param a : "first number"
 @param b : "second"  "number"
*>
fn int add(int a, int b = 1) => a + b;

<*
 @param y : "the y"
*>
fn int sub(int x, int y) => x - y;

fn void main()
{
	var $p = $Typeof(&add)::params;
	$assert $p[0].param == "first number";
	$assert $p[1].param == "secondnumber";
	$p = $Typeof(&sub)::params;
	$assert $p[0].param == "";
	$assert $p[1].param == "the y";
}
